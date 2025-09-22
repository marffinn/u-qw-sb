
from setuptools import setup

setup(
    name='BROWSANKA',
    version='0.1.0',
    description='A QuakeWorld server browser',
    author='Your Name',
    author_email='your.email@example.com',
    packages=['browsanka'],
    install_requires=[
        'beautifulsoup4==4.12.3',
        'certifi==2024.2.2',
        'charset-normalizer==3.3.2',
        'idna==3.7',
        'lxml==5.2.1',
        'PyQt6==6.7.0',
        'PyQt6-sip==13.6.0',
        'python-dotenv==1.0.1',
        'requests==2.31.0',
        'soupsieve==2.5',
        'urllib3==2.2.1',
    ],
)
