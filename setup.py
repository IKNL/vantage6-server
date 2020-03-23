from os import path
from codecs import open
from setuptools import setup, find_namespace_packages

# get current directory
here = path.abspath(path.dirname(__file__))

# get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# read the API version from disk 
with open(path.join(here, 'vantage6', 'VERSION')) as fp:
    __version__ = fp.read()

# setup the package
setup(
    name='vantage6-server',
    version=__version__,
    description='Vantage6 server',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/IKNL/vantage6-server',
    packages=find_namespace_packages(),
    python_requires='>=3.6',
    install_requires=[
        'appdirs==1.4.3',
        'flask==1.1.1',
        'Flask-RESTful==0.3.8',
        'Flask-Cors==3.0.8',
        'Flask-JWT-Extended==3.24.1',
        'flask-marshmallow==0.11.0',
        'Flask-SocketIO==4.2.1',
        'Flask-SQLAlchemy==2.4.1',
        'iknl-flasgger==0.9.2.post1',
        'schema==0.7.1',
        'bcrypt==3.1.7',
        'questionary==1.5.1',
        'marshmallow==2.16.3',
        'marshmallow-sqlalchemy==0.15.0',
        'ipython==7.13.0',
        'requests==2.23.0',
        'psutil==5.7.0',
        'gevent==1.4.0'
    ],
    extras_require={
        'dev':[
            'termcolor==1.1.0',
            'coverage==5.0.4'
        ]
    },
    package_data={  
        'vantage6': [
            'VERSION',
            '_data/**/*.yaml',
            '_data/*.yaml',
            'server/resource/swagger/*.yaml'
        ],
    },
    entry_points={
        'console_scripts': [
            'vserver=vantage6.server.cli.server:cli_server'
        ]
    }
)