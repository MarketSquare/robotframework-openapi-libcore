# pylint: disable=missing-function-docstring, unused-argument
# monkey-patch for 3.11 compatibility, see https://github.com/pyinvoke/invoke/issues/833
import inspect
import pathlib
import subprocess
from importlib.metadata import version

if not hasattr(inspect, "getargspec"):
    inspect.getargspec = inspect.getfullargspec

from invoke import task

from OpenApiLibCore import openapi_libcore

ROOT = pathlib.Path(__file__).parent.resolve().as_posix()
VERSION = version("robotframework-openapi-libcore")


@task
def testserver(context):
    cmd = [
        "python",
        "-m",
        "uvicorn",
        "testserver:app",
        f"--app-dir {ROOT}/tests/server",
        "--host 0.0.0.0",
        "--port 8000",
        "--reload",
        f"--reload-dir {ROOT}/tests/server",
    ]
    subprocess.run(" ".join(cmd), shell=True, check=False)


@task
def utests(context):
    cmd = [
        "coverage",
        "run",
        "-m",
        "unittest",
        "discover ",
        f"{ROOT}/tests/unittests",
    ]
    subprocess.run(" ".join(cmd), shell=True, check=False)


@task
def atests(context):
    cmd = [
        "coverage",
        "run",
        "-m",
        "robot",
        f"--argumentfile={ROOT}/tests/rf_cli.args",
        f"--variable=root:{ROOT}",
        f"--outputdir={ROOT}/tests/logs",
        "--loglevel=TRACE:DEBUG",
        f"{ROOT}/tests/suites",
    ]
    subprocess.run(" ".join(cmd), shell=True, check=False)


@task(utests, atests)
def tests(context):
    subprocess.run("coverage combine", shell=True, check=False)
    subprocess.run("coverage report", shell=True, check=False)
    subprocess.run("coverage html", shell=True, check=False)


@task
def lint(context):
    subprocess.run(f"mypy {ROOT}", shell=True, check=False)
    subprocess.run(f"pylint {ROOT}/src/OpenApiLibCore", shell=True, check=False)


@task
def format_code(context):
    subprocess.run(f"black {ROOT}", shell=True, check=False)
    subprocess.run(f"isort {ROOT}", shell=True, check=False)
    subprocess.run(f"robotidy {ROOT}", shell=True, check=False)


@task
def libdoc(context):
    json_file = f"{ROOT}/tests/files/petstore_openapi.json"
    source = f"OpenApiLibCore::{json_file}"
    target = f"{ROOT}/docs/openapi_libcore.html"
    cmd = [
        "python",
        "-m",
        "robot.libdoc",
        f"-v {VERSION}",
        source,
        target,
    ]
    subprocess.run(" ".join(cmd), shell=True, check=False)


@task
def libspec(context):
    json_file = f"{ROOT}/tests/files/petstore_openapi.json"
    source = f"OpenApiLibCore::{json_file}"
    target = f"{ROOT}/src/OpenApiLibCore/openapi_libcore.libspec"
    cmd = [
        "python",
        "-m",
        "robot.libdoc",
        f"-v {VERSION}",
        source,
        target,
    ]
    subprocess.run(" ".join(cmd), shell=True, check=False)


@task
def readme(context):
    #     front_matter = (
    # r"""---
    # [![CI](https://github.com/MarketSquare/robotframework-openapi-libcore/actions/workflows/ci.yml/badge.svg)](https://github.com/MarketSquare/robotframework-openapi-libcore/actions/workflows/ci.yml
    # ![[Unit-tests](https://img.shields.io/github/workflow/status/MarketSquare/robotframework-openapi-libcore/Unit%20tests/main)](https://github.com/MarketSquare/robotframework-openapi-libcore/actions?query=workflow%3A%22Unit+tests%22 "GitHub Workflow Unit Tests Status")
    # ![Codecov](https://img.shields.io/codecov/c/github/MarketSquare/robotframework-openapi-libcore/main "Code coverage on master branch")
    # ![PyPI](https://img.shields.io/pypi/v/robotframework-openapi-libcore?label=version "PyPI package version")
    # ![Python versions](https://img.shields.io/pypi/pyversions/robotframework-openapi-libcore "Supported Python versions")
    # ![Licence](https://img.shields.io/pypi/l/robotframework-openapi-libcore "PyPI - License")
    # ---
    # """)
    front_matter = """---\n---\n"""
    with open(f"{ROOT}/docs/README.md", "w", encoding="utf-8") as readme:
        doc_string = openapi_libcore.__doc__
        readme.write(front_matter)
        readme.write(str(doc_string).replace("\\", "\\\\").replace("\\\\*", "\\*"))


@task(format_code, libdoc, libspec, readme)
def build(context):
    subprocess.run("poetry build", shell=True, check=False)


@task(post=[build])
def bump_version(context, rule):
    subprocess.run(f"poetry version {rule}", shell=True, check=False)
    subprocess.run("poetry install", shell=True, check=False)
