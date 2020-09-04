import time
import tempfile
from pathlib import Path
from random import randint
from subprocess import check_output
from urllib.parse import unquote

import pytest

import gitlab


TEMP_DIR = tempfile.gettempdir()
TEST_DIR = Path(__file__).resolve().parent


def random_id():
    """
    Helper to ensure new resource creation does not clash with
    existing resources, for example when a previous test deleted a
    resource but GitLab is still deleting it asynchronously in the
    background. TODO: Expand to make it 100% safe.
    """
    return randint(9, 9999)


def reset_gitlab(gl):
    for project in gl.projects.list():
        project.delete()
    for group in gl.groups.list():
        group.delete()
    for user in gl.users.list():
        if user.username != "root":
            user.delete()


def set_token(container):
    set_token = TEST_DIR / "fixtures" / "set_token.rb"

    with open(set_token, "r") as f:
        set_token_command = f.read().strip()

    rails_command = [
        "docker",
        "exec",
        container,
        "gitlab-rails",
        "runner",
        set_token_command,
    ]
    output = check_output(rails_command).decode()

    return output


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return TEST_DIR / "fixtures" / "docker-compose.yml"


@pytest.fixture(scope="session")
def check_is_alive(request):
    """
    Return a healtcheck function fixture for the GitLab container spinup.
    """
    start = time.time()

    def _check(container):
        delay = int(time.time() - start)

        # Temporary manager to disable capsys in a session-scoped fixture
        # so people know it takes a while for GitLab to spin up
        # https://github.com/pytest-dev/pytest/issues/2704
        capmanager = request.config.pluginmanager.getplugin("capturemanager")
        with capmanager.global_and_fixture_disabled():
            print(f"Waiting for GitLab to reconfigure.. (~{delay}s)")

        logs = ["docker", "logs", container]
        output = check_output(logs).decode()

        return "gitlab Reconfigured!" in output

    return _check


@pytest.fixture(scope="session")
def CONFIG(docker_ip, docker_services):
    config_file = Path(TEMP_DIR) / "python-gitlab.cfg"

    ip = unquote(docker_ip)
    port = docker_services.port_for("gitlab", 80)

    config = f"""[global]
    default = local
    timeout = 60

    [local]
    url = http://{docker_ip}:{port}
    private_token = python-gitlab-token
    api_version = 4"""

    with open(config_file, "w") as f:
        f.write(config)

    return config_file


@pytest.fixture(scope="session")
def gl(CONFIG, docker_services, request, check_is_alive):
    """Helper instance to make fixtures and asserts directly via the API."""

    docker_services.wait_until_responsive(
        timeout=180, pause=5, check=lambda: check_is_alive("gitlab-test")
    )

    set_token("gitlab-test")

    instance = gitlab.Gitlab.from_config("local", [CONFIG])
    reset_gitlab(instance)

    return instance


@pytest.fixture(scope="module")
def group(gl):
    """Group fixture for group API resource tests."""
    _id = random_id()
    data = {
        "name": f"test-group-{_id}",
        "path": f"group-{_id}",
    }
    group = gl.groups.create(data)

    yield group

    try:
        group.delete()
    except gitlab.exceptions.GitlabDeleteError as e:
        print(f"Group already deleted: {e}")


@pytest.fixture(scope="module")
def project(gl):
    """Project fixture for project API resource tests."""
    _id = random_id()
    name = f"test-project-{_id}"

    project = gl.projects.create(name=name)

    yield project

    try:
        project.delete()
    except gitlab.exceptions.GitlabDeleteError as e:
        print(f"Project already deleted: {e}")


@pytest.fixture(scope="module")
def user(gl):
    """User fixture for user API resource tests."""
    _id = random_id()
    email = f"user{_id}@email.com"
    username = f"user{_id}"
    name = f"User {_id}"
    password = "fakepassword"

    user = gl.users.create(email=email, username=username, name=name, password=password)

    yield user

    try:
        user.delete()
    except gitlab.exceptions.GitlabDeleteError as e:
        print(f"User already deleted: {e}")


@pytest.fixture(scope="module")
def issue(project):
    """Issue fixture for issue API resource tests."""
    _id = random_id()
    data = {"title": f"Issue {_id}", "description": f"Issue {_id} description"}

    return project.issues.create(data)


@pytest.fixture(scope="module")
def label(project):
    """Label fixture for project label API resource tests."""
    _id = random_id()
    data = {
        "name": f"prjlabel{_id}",
        "description": f"prjlabel1 {_id} description",
        "color": "#112233",
    }

    return project.labels.create(data)


@pytest.fixture(scope="module")
def group_label(group):
    """Label fixture for group label API resource tests."""
    _id = random_id()
    data = {
        "name": f"grplabel{_id}",
        "description": f"grplabel1 {_id} description",
        "color": "#112233",
    }

    return group.labels.create(data)


@pytest.fixture(scope="module")
def variable(project):
    """Variable fixture for project variable API resource tests."""
    _id = random_id()
    data = {"key": f"var{_id}", "value": f"Variable {_id}"}

    return project.variables.create(data)


@pytest.fixture(scope="module")
def deploy_token(project):
    """Deploy token fixture for project deploy token API resource tests."""
    _id = random_id()
    data = {
        "name": f"token-{_id}",
        "username": "root",
        "expires_at": "2021-09-09",
        "scopes": "read_registry",
    }

    return project.deploytokens.create(data)


@pytest.fixture(scope="module")
def group_deploy_token(group):
    """Deploy token fixture for group deploy token API resource tests."""
    _id = random_id()
    data = {
        "name": f"group-token-{_id}",
        "username": "root",
        "expires_at": "2021-09-09",
        "scopes": "read_registry",
    }

    return group.deploytokens.create(data)
