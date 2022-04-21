from setuptools import setup
from Cython.Build import cythonize

setup(ext_modules=cythonize('C:\\Users\\84430\\Desktop\\lda-2.0.0\\lda\\_lda.pyx'))