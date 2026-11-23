"""CI push mirror of main and tags; credentials never enter a remote URL or output."""
import base64
import os
import subprocess

env = dict(os.environ)
token = env.pop("GITHUB_MIRROR_TOKEN")
env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraHeader",
           GIT_CONFIG_VALUE_0="Authorization: Basic " + base64.b64encode(("x-access-token:" + token).encode()).decode())
subprocess.run(["git", "push", "https://github.com/cad-lab-ai/mini-capp.git", "HEAD:refs/heads/main", "--tags"],
               env=env, check=True)
