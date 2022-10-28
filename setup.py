import os

from setuptools import find_packages, setup
from setuptools.version import __version__ as setuptools_version

if tuple(map(int, setuptools_version.split(".")[:2])) < (40, 0):
    import sys

    python = sys.executable
    try:
        s = os.system(f'{python} -m pip install "setuptools>=40"')
        if s != 0:
            raise Exception
    except Exception:
        raise Exception("Setuptools>40 have to be installed")

    os.execl(python, python, *sys.argv)


with open(os.path.join("version.txt")) as version_file:
    version_from_file = version_file.read().strip()

with open("requirements.txt") as f_required:
    required = f_required.read().splitlines()

with open("test_requirements.txt") as f_tests:
    required_for_tests = f_tests.read().splitlines()


description = (
    "A repository for projects providing out of the box capabilities within "
    "CloudShell to define AWS instances in CloudShell and leverage Amazon Cloud "
    "Computing capabilities to deploy and connect apps in CloudShell sandboxes."
)

setup(
    name="cloudshell-cp-aws",
    url="http://www.qualisystems.com/",
    author="QualiSystems",
    author_email="info@qualisystems.com",
    packages=find_packages(),
    install_requires=required,
    tests_require=required_for_tests,
    python_requires="~=3.7",
    version=version_from_file,
    package_data={"": ["*.txt"]},
    description=description,
    long_description=description,
    include_package_data=True,
)
