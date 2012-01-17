from setuptools import setup

setup(
    name = "django-googlemail-backend",
    version = __import__("googlemail_backend").__version__,
    author = "Glenn Washburn",
    author_email = "development@efficientek.com",
    description = "A Django email backend for sending via googlemail's SMTP.",
    url = "http://github.com/crass/django-googlemail-backend",
    license = "MIT",
    packages = [
        "googlemail_backend",
    ],
    classifiers = [
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Utilities",
        "Framework :: Django",
    ]
)
