import setuptools

with open('requirements.txt') as f:
    requirements = [line.rstrip('\n') for line in f if not line.startswith('#')]

setuptools.setup(
    name='decisionlib-cli-mhentges',
    version='0.0.3',
    author='Mozilla Release Engineering',
    author_email='release+python@mozilla.com',
    description='Taskcluster task-builder',
    packages=setuptools.find_packages(),
    install_requires=requirements,
    include_package_data=True,
    python_requires='~=2.7',
    entry_points={
        'console_scripts': [
            'decisionlib-cli = decisionlib:main',
        ],
    },
)
