import setuptools

with open('requirements.txt') as f:
    requirements = [line.rstrip('\n') for line in f if not line.startswith('#')]

setuptools.setup(
    name='decisionlib-mhentges',
    version='0.0.30',
    author='Mozilla Release Engineering',
    author_email='release+python@mozilla.com',
    description='Taskcluster task-builder',
    packages=setuptools.find_packages(),
    install_requires=requirements,
    include_package_data=True,
    python_requires='>=3.6',
    entry_points={
        'console_scripts': [
            'decisionlib = decisionlib:main',
        ],
    },
)
