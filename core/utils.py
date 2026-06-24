import os
import sys


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def application_path(relative_path=""):
    base_path = application_base_dirs()[0]

    if not relative_path:
        return base_path

    return os.path.join(base_path, relative_path)


def application_base_dirs():
    dirs = []
    seen = set()

    def add(path):
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in seen:
            return
        seen.add(normalized)
        dirs.append(os.path.abspath(path))

    if getattr(sys, "frozen", False):
        add(os.path.dirname(os.path.abspath(sys.executable)))
        add(os.getcwd())
        add(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))))
    else:
        add(os.path.abspath("."))
        if sys.argv and sys.argv[0]:
            add(os.path.dirname(os.path.abspath(sys.argv[0])))
        add(os.getcwd())

    return dirs


def ensure_application_cwd():
    if getattr(sys, "frozen", False):
        os.chdir(application_path())


def _directory_has_beatmaps(path):
    if not os.path.isdir(path):
        return False

    try:
        for entry in os.scandir(path):
            if not entry.is_dir():
                continue
            for child in os.scandir(entry.path):
                if child.is_file() and child.name.endswith(".osu"):
                    return True
    except OSError:
        return False

    return False


def discover_user_data_directories(name):
    env_var = f"PYOSU_{name.upper()}_DIR"
    override = os.environ.get(env_var)
    if override:
        return [os.path.abspath(override)]

    candidates = []
    seen = set()

    for base in application_base_dirs():
        candidate = os.path.join(base, name)
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(candidate)

    with_beatmaps = [
        path for path in candidates if _directory_has_beatmaps(path)
    ]
    if with_beatmaps:
        return with_beatmaps

    existing = [path for path in candidates if os.path.isdir(path)]
    if existing:
        return existing

    return [candidates[0]] if candidates else [application_path(name)]


def resolve_user_data_path(name, *, create_default=True):
    directories = discover_user_data_directories(name)
    selected = directories[0]

    if create_default and not os.path.exists(selected):
        os.makedirs(selected, exist_ok=True)

    return selected
