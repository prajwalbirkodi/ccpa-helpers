from setuptools import setup, find_packages
import pathlib

local_path = pathlib.Path(__file__).parent
install_requires = (local_path / "requirements.txt").read_text().splitlines()

setup(
    name="ccpa-helpers",
    use_scm_version=True,
    setup_requires=["setuptools", "setuptools_scm"],
    package_dir={"": "src"},
    install_requires=install_requires,
    python_requires=">=3.7",
    packages=find_packages(where="src/ccpa-helpers"),
    package_data={"": ["*.yaml"]},
    include_package_data=True,
    description="Synthetic Data for CCPA",
    url="https://github.com/gretelai/ccpa-helpers",
    license="https://gretel.ai/license/source-available-license",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: Free To Use But Restricted",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    entry_points={
        'console_scripts': [
            'ccpa-synthetics=app:main',
        ],
    },
)
