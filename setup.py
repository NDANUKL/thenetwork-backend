from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n") if True else []

setup(
    name="fieldpulse",
    version="0.0.1",
    description="Offline-first geo-coded task platform for field agents",
    author="FieldPulse Team",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[],
)
