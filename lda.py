# coding=utf-8
"""Latent Dirichlet allocation using collapsed Gibbs sampling"""

from __future__ import absolute_import, division, unicode_literals  # noqa
import logging
import sys

import numpy as np
from scipy.spatial.distance import cosine
import random
import math
import heapq
import tqdm

import lda._lda
import lda.utils

logger = logging.getLogger('lda')

PY2 = sys.version_info[0] == 2
if PY2:
    range = xrange  # noqa


class LDA:
    """Latent Dirichlet allocation using collapsed Gibbs sampling

    Parameters
    ----------
    n_topics : int
        Number of topics

    n_iter : int, default 2000
        Number of sampling iterations

    alpha : float, default 0.1
        Dirichlet parameter for distribution over topics

    eta : float, default 0.01
        Dirichlet parameter for distribution over words

    random_state : int or RandomState, optional
        The generator used for the initial topics.

    Attributes
    ----------
    `components_` : array, shape = [n_topics, n_features]
        Point estimate of the topic-word distributions (Phi in literature)
    `topic_word_` :
        Alias for `components_`
    `nzw_` : array, shape = [n_topics, n_features]
        Matrix of counts recording topic-word assignments in final iteration.
    `ndz_` : array, shape = [n_samples, n_topics]
        Matrix of counts recording document-topic assignments in final iteration.
    `doc_topic_` : array, shape = [n_samples, n_features]
        Point estimate of the document-topic distributions (Theta in literature)
    `nz_` : array, shape = [n_topics]
        Array of topic assignment counts in final iteration.

    Examples
    --------
    >>> import numpy
    >>> X = numpy.array([[1,1], [2, 1], [3, 1], [4, 1], [5, 8], [6, 1]])
    >>> import lda
    >>> model = lda.LDA(n_topics=2, random_state=0, n_iter=100)
    >>> model.fit(X) #doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
    LDA(alpha=...
    >>> model.components_
    array([[ 0.85714286,  0.14285714],
           [ 0.45      ,  0.55      ]])
    >>> model.loglikelihood() #doctest: +ELLIPSIS
    -40.395...

    References
    ----------
    Blei, David M., Andrew Y. Ng, and Michael I. Jordan. "Latent Dirichlet
    Allocation." Journal of Machine Learning Research 3 (2003): 993???1022.

    Griffiths, Thomas L., and Mark Steyvers. "Finding Scientific Topics."
    Proceedings of the National Academy of Sciences 101 (2004): 5228???5235.
    doi:10.1073/pnas.0307752101.

    Wallach, Hanna, David Mimno, and Andrew McCallum. "Rethinking LDA: Why
    Priors Matter." In Advances in Neural Information Processing Systems 22,
    edited by Y.  Bengio, D. Schuurmans, J. Lafferty, C. K. I. Williams, and A.
    Culotta, 1973???1981, 2009.

    Wallach, Hanna M., Iain Murray, Ruslan Salakhutdinov, and David Mimno. 2009.
    ???Evaluation Methods for Topic Models.??? In Proceedings of the 26th Annual
    International Conference on Machine Learning, 1105???1112. ICML ???09. New York,
    NY, USA: ACM. https://doi.org/10.1145/1553374.1553515.

    Buntine, Wray. "Estimating Likelihoods for Topic Models." In Advances in
    Machine Learning, First Asian Conference on Machine Learning (2009): 51???64.
    doi:10.1007/978-3-642-05224-8_6.

    """

    def __init__(self, n_topics, wv, id2word, n_iter=2000, alpha=0.1, eta=0.01, lamda=0.5, random_state=None,
                 refresh=10):
        self.n_topics = n_topics
        self.n_iter = n_iter
        self.alpha = alpha
        self.eta = eta
        self.lamda = lamda
        self.wv = wv
        self.id2word = id2word
        # if random_state is None, check_random_state(None) does nothing
        # other than return the current numpy RandomState
        self.random_state = random_state
        self.refresh = refresh

        if alpha <= 0 or eta <= 0:
            raise ValueError("alpha and eta must be greater than zero")

        # random numbers that are reused
        rng = lda.utils.check_random_state(random_state)
        self._rands = rng.rand(1024**2 // 8)  # 1MiB of random variates

        # configure console logging if not already configured
        if len(logger.handlers) == 1 and isinstance(logger.handlers[0], logging.NullHandler):
            logging.basicConfig(level=logging.INFO)

    def fit(self, X, y=None):
        """Fit the model with X.

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            Training data, where n_samples in the number of samples
            and n_features is the number of features. Sparse matrix allowed.

        Returns
        -------
        self : object
            Returns the instance itself.
        """
        self._fit(X)
        return self

    def fit_transform(self, X, y=None):
        """Apply dimensionality reduction on X

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            New data, where n_samples in the number of samples
            and n_features is the number of features. Sparse matrix allowed.

        Returns
        -------
        doc_topic : array-like, shape (n_samples, n_topics)
            Point estimate of the document-topic distributions

        """
        if isinstance(X, np.ndarray):
            # in case user passes a (non-sparse) array of shape (n_features,)
            # turn it into an array of shape (1, n_features)
            X = np.atleast_2d(X)
        self._fit(X)
        return self.doc_topic_

    def transform(self, X, max_iter=20, tol=1e-16):
        """Transform the data X according to previously fitted model

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            New data, where n_samples in the number of samples
            and n_features is the number of features.
        max_iter : int, optional
            Maximum number of iterations in iterated-pseudocount estimation.
        tol: double, optional
            Tolerance value used in stopping condition.

        Returns
        -------
        doc_topic : array-like, shape (n_samples, n_topics)
            Point estimate of the document-topic distributions

        Note
        ----
        To calculate an approximation of the distribution over topics for each
        new document this function uses the "iterated pseudo-counts" approach
        described in Wallach, Murray, Salakhutdinov, and Mimno (2009) and
        justified in greater detail in Buntine (2009). Specifically, we
        implement the "simpler first order version" described in section 3.3 of
        Buntine (2009).

        """
        if isinstance(X, np.ndarray):
            # in case user passes a (non-sparse) array of shape (n_features,)
            # turn it into an array of shape (1, n_features)
            X = np.atleast_2d(X)
        doc_topic = np.empty((X.shape[0], self.n_topics))
        WS, DS = lda.utils.matrix_to_lists(X)
        # TODO: this loop is parallelizable
        for d in np.unique(DS):
            doc_topic[d] = self._transform_single(WS[DS == d], max_iter, tol)
        return doc_topic

    def _transform_single(self, doc, max_iter, tol):
        """Transform a single document according to the previously fit model

        Parameters
        ----------
        X : 1D numpy array of integers
            Each element represents a word in the document
        max_iter : int
            Maximum number of iterations in iterated-pseudocount estimation.
        tol: double
            Tolerance value used in stopping condition.

        Returns
        -------
        doc_topic : 1D numpy array of length n_topics
            Point estimate of the topic distributions for document

        Note
        ----

        See Note in `transform` documentation.

        """
        PZS = np.zeros((len(doc), self.n_topics))
        for iteration in range(max_iter + 1):  # +1 is for initialization
            PZS_new = self.components_[:, doc].T
            PZS_new *= (PZS.sum(axis=0) - PZS + self.alpha)
            PZS_new /= PZS_new.sum(axis=1)[:, np.newaxis]  # vector to single column matrix
            delta_naive = np.abs(PZS_new - PZS).sum()
            logger.debug('transform iter {}, delta {}'.format(iteration, delta_naive))
            PZS = PZS_new
            if delta_naive < tol:
                break
        theta_doc = PZS.sum(axis=0) / PZS.sum()
        assert len(theta_doc) == self.n_topics
        assert theta_doc.shape == (self.n_topics,)
        return theta_doc
    
    def perplexity(self, X):
        """Calculate the perplexity score of the topic model

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            Training vector, where n_samples in the number of samples and
            n_features is the number of features. Sparse matrix allowed.
        """
        N = int(X.sum())
        sum = 0
        for d in range(X.shape[0]):
            prob_doc = 0.0 # the probablity of the doc
            for i in range(X.shape[1]):
                if X[d,i] != 0:
                    prob_word = 0 # the probablity of the word
                    for k in range(self.n_topics):
                        # cal p(w) = sumz(p(z|d)*p(w|z))
                        prob_word += self.doc_topic_[d,k] * self.topic_word_[k,i]
                    prob_doc += X[d,i] * math.log(prob_word)
            sum += prob_doc
        perplexity_score = math.exp(-sum/N)
        return perplexity_score

    def _fit(self, X):
        """Fit the model to the data X

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            Training vector, where n_samples in the number of samples and
            n_features is the number of features. Sparse matrix allowed.
        """
        random_state = lda.utils.check_random_state(self.random_state)
        rands = self._rands.copy()
        self._initialize(X)
        for it in tqdm.tqdm(range(self.n_iter)):
            # FIXME: using numpy.roll with a random shift might be faster
            random_state.shuffle(rands)
            if it % self.refresh == 0:
                ll = self.loglikelihood()
                #logger.info("<{}> log likelihood: {:.0f}".format(it, ll))
                # keep track of loglikelihoods for monitoring convergence
                self.loglikelihoods_.append(ll)
            self._sample_topics(rands)

            #woc2vec??????
            if it%2 == 0:
                self.components_ = (self.nzw_ + self.eta).astype(float)
                self.components_ /= np.sum(self.components_, axis=1)[:, np.newaxis]
                topic_word_ = self.components_ # topic * word
                self.topic_word_new = self.components_
                #????????????????????????
                topic_most = np.zeros((self.n_topics, 12), dtype=int)
                ck = np.zeros((self.n_topics), dtype=float)
                count = np.zeros((self.n_topics*12, X.shape[0], self.n_topics), dtype=float)
                for i in range(self.n_topics):
                    topic_most[i] = topic_word_[i].argsort()[::-1][0:12]
                word_id = topic_most.tolist()
                for i in range(int(X.sum())):
                    w, d, z = self.WS[i], self.DS[i], self.ZS[i]
                    if w in word_id[z]:
                        count[word_id[z].index(w) + 12*z,d,z] += 1
                for i in range(self.n_topics):
                    for m in range(i * 12 + 1, i * 12 + 12):
                        for l in range(i * 12, m):
                            con_frequency = 0
                            self_frequency = 0
                            for d in range(X.shape[0]):
                                #???????????????????????????
                                if count[m, d, i] != 0 and count[l, d, i] != 0:
                                    con_frequency += 1
                                if count[l, d, i] != 0:
                                    self_frequency += 1
                            ck[i] += math.log((con_frequency + 1)/ self_frequency)
                ck_sum = np.sum(ck)
                adjust = 0
                ck_min = ck[0] - (ck_sum - ck[0]) / (self.n_topics - 1)
                for i in range(1, self.n_topics):
                    if ck[i] - (ck_sum - ck[i]) / (self.n_topics - 1) < ck_min:
                        ck_min = ck[i] - (ck_sum - ck[i]) / (self.n_topics - 1)
                        adjust = i
                #if it == self.n_iter - 1:
                    #print(ck_sum/self.n_topics)

                #??????Doc2vec??????eta??????
                min_rele = []
                p_allocate = 0
                p_allocate_sum = 0
                total_embedding = np.zeros((100), dtype=float)
                for i in range(12):
                    total_embedding += self.wv[self.id2word[topic_most[adjust, i]]]
                total_embedding /= 12
                for i in range(12):
                    min_rele.append(1 - cosine(self.wv[self.id2word[topic_most[adjust, i]]], total_embedding))
                #min_number = heapq.nsmallest(5, m)
                min_index = list(map(min_rele.index, heapq.nsmallest(5, min_rele))) 
                for i in min_index:
                    adjust_id = topic_most[adjust,i]
                    if min_rele[i] > 0:
                        self.topic_word_new[adjust,adjust_id] *= min_rele[i]
                        p_allocate += self.topic_word_new[adjust, adjust_id] * (1 - min_rele[i])
                    else:
                        self.topic_word_new[adjust,adjust_id] *= 0
                        p_allocate += self.topic_word_new[adjust, adjust_id]
                for i in range(12):
                    if i not in min_index:
                        p_id = topic_most[adjust,i]
                        p_allocate_sum += self.topic_word_new[adjust,p_id]
                for i in range(12):
                    if i not in min_index:
                        p_id = topic_most[adjust, i]
                        self.topic_word_new[adjust,p_id] *= (1 + p_allocate * self.topic_word_new[adjust,p_id] / p_allocate_sum)
                #u = random.random()


                                    
        ll = self.loglikelihood()
        logger.info("<{}> log likelihood: {:.0f}".format(self.n_iter - 1, ll))
        # note: numpy /= is integer division
        self.components_ = (self.nzw_ + self.eta).astype(float) # topic-word
        self.components_ /= np.sum(self.components_, axis=1)[:, np.newaxis]
        self.topic_word_ = self.components_ # topic * word
        self.doc_topic_ = (self.ndz_ + self.alpha).astype(float)
        self.doc_topic_ /= np.sum(self.doc_topic_, axis=1)[:, np.newaxis]
        self.topic_word_ = self.lamda * self.topic_word_ + (1 - self.lamda) * self.topic_word_new
        print(self.perplexity(X))

        # delete attributes no longer needed after fitting to save memory and reduce clutter
        del self.WS
        del self.DS
        del self.ZS
        return self

    def _initialize(self, X):
        D, W = X.shape #D???????????????W????????????
        N = int(X.sum()) #N??????????????????????????????????????????
        n_topics = self.n_topics
        n_iter = self.n_iter
        logger.info("n_documents: {}".format(D))
        logger.info("vocab_size: {}".format(W))
        logger.info("n_words: {}".format(N))
        logger.info("n_topics: {}".format(n_topics))
        logger.info("n_iter: {}".format(n_iter))

        self.nzw_ = nzw_ = np.zeros((n_topics, W), dtype=np.intc) #??????-????????????
        self.ndz_ = ndz_ = np.zeros((D, n_topics), dtype=np.intc) #??????-????????????
        self.nz_ = nz_ = np.zeros(n_topics, dtype=np.intc) #nz?????????i?????????????????????????????????
        self.WS, self.DS = WS, DS = lda.utils.matrix_to_lists(X) #WS??????i???????????????id???DS??????i???????????????docid
        self.ZS = ZS = np.empty_like(self.WS, dtype=np.intc) #ZS??????i???????????????topicid

        #?????????????????????
        self.components_ = (self.nzw_ + self.eta).astype(float)
        self.components_ /= np.sum(self.components_, axis=1)[:, np.newaxis]
        self.topic_word_new = self.components_
        np.testing.assert_equal(N, len(WS))
        for i in range(N):
            w, d = WS[i], DS[i]
            z_new = i % n_topics
            ZS[i] = z_new
            ndz_[d, z_new] += 1
            nzw_[z_new, w] += 1
            nz_[z_new] += 1
        self.loglikelihoods_ = []

    def loglikelihood(self):
        """Calculate complete log likelihood, log p(w,z)

        Formula used is log p(w,z) = log p(w|z) + log p(z)
        """
        nzw, ndz, nz = self.nzw_, self.ndz_, self.nz_
        alpha = self.alpha
        eta = self.eta
        nd = np.sum(ndz, axis=1).astype(np.intc)
        return lda._lda._loglikelihood(nzw, ndz, nz, nd, alpha, eta)

    def _sample_topics(self, rands):
        """Samples all topic assignments. Called once per iteration."""
        n_topics, vocab_size = self.nzw_.shape
        alpha = np.repeat(self.alpha, n_topics).astype(np.float64)
        eta = np.repeat(self.eta, vocab_size).astype(np.float64)
        lda._lda._sample_topics(self.WS, self.DS, self.ZS, self.nzw_, self.ndz_, self.nz_,
                                alpha, eta, rands, self.lamda, self.topic_word_new)
