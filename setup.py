from setuptools import find_packages, setup

with open('README.md', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='pyre-starlette',
    version='1.0.0',
    author='且听风吟、我是指针*、ZDLAY、KYZ',
    author_email='breezechime@163.com',
    description='基于 Starlette 的异步 Web 框架：控制器路由、参数注入、依赖注入、统一响应、OpenAPI 与代码生成',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/breezechime/pyre-starlette',
    project_urls={
        'Source': 'https://github.com/breezechime/pyre-starlette',
        'Issues': 'https://github.com/breezechime/pyre-starlette/issues',
    },
    license='MIT',
    packages=find_packages(exclude=('tests', 'tests.*', 'examples', 'examples.*')),
    package_data={
        'pyre_starlette': ['py.typed', 'templates/*.html'],
        'pyre_starlette.openapi': ['templates/*.html'],
        'pyre_starlette.applications.code_generator': [
            'templates/*.j2',
            'templates/*/*.j2',
            'templates/*/*/*.j2',
            'templates/*/*/*/*.j2',
        ],
    },
    include_package_data=True,
    python_requires='>=3.10',
    install_requires=[
        'starlette>=1.0',
        'pydantic>=2.0',
        'colorlog>=6.0',
        'Jinja2>=3.0',
        'pyre-config>=1.0.0',
        'pyre-injector>=1.0.0',
        'pyre-sqlalchemy-db>=1.0.0',
    ],
    extras_require={
        'cli': ['uvicorn'],
        'auth': ['authlib>=1.0', 'werkzeug>=2.0'],
        'redis': ['redis>=4.0'],
        'scheduler': ['apscheduler>=3.10'],
        'async': ['greenlet', 'aiosqlite'],
        'all': [
            'uvicorn',
            'authlib>=1.0',
            'werkzeug>=2.0',
            'redis>=4.0',
            'apscheduler>=3.10',
            'greenlet',
            'aiosqlite',
        ],
    },
    entry_points={
        'console_scripts': [
            'pyre=pyre_starlette.cli:main',
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Framework :: AsyncIO',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='starlette asgi web framework async restful openapi dependency-injection controller routing',
)
