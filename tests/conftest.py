import os


# Tests are fully offline and never load provider credentials from files or the
# environment. Runtime metrics stay disabled unless a test opts in explicitly.
os.environ["METRICS_ENABLED"] = "false"
