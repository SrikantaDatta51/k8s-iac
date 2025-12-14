import requests
import time
import sys

# Configuration
GITEA_URL = "http://192.168.100.10:30300"
USER = "gitea_admin"
PASS = "gitea_admin_password"
EMAIL = "admin@example.com"
REPO_NAME = "gitops-repo"

def wait_for_gitea():
    print("Waiting for Gitea to be ready...")
    for i in range(30):
        try:
            r = requests.get(GITEA_URL)
            if r.status_code == 200:
                print("Gitea is up!")
                return True
        except:
            pass
        time.sleep(2)
    print("Gitea failed to start.")
    return False

def create_user():
    # In a real install, we'd use the `gitea admin user create` CLI command inside the pod
    # But checking if we can hitting the install page/API
    # Since this is a fresh install with SQLite, the first user registered becomes admin
    # However, automating the "Install" page click-through via script is hard without Selenium.
    # BETTER APPROACH: Run `gitea admin user create` via kubectl exec.
    pass

if __name__ == "__main__":
    if not wait_for_gitea():
        sys.exit(1)
    
    # We will handle the actual creation in the shell script wrapper using kubectl exec
    print("Gitea is reachable.")
