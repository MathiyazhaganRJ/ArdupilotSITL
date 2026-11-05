# ArduPilot SITL Git Workflow & Multi-OS Synchronization Guide

A complete reference for managing branches, synchronizing code between Windows and Linux environments, and pushing/pulling updates with GitHub.

---

## 1. Core Concept: What is `origin`?

When you clone a repository from GitHub:
- `origin` is the shorthand alias Git creates for the remote repository URL (`https://github.com/MathiyazhaganRJ/ArdupilotSITL.git`).
- A branch name alone (e.g. `feature/lxnav-hud`) refers to your **local machine's copy**.
- `origin/feature/lxnav-hud` refers to the **version stored on GitHub**.

### Why specifying `origin` matters:
Running plain `git pull` often fails with:
`There is no tracking information for the current branch.`
By explicitly typing:
```bash
git pull origin <branch-name>
```
you tell Git exactly where to fetch the code from (`origin`) and which branch stream to merge (`<branch-name>`).

> **Tip:** If you set upstream tracking once using `git push -u origin <branch-name>`, Git remembers the relationship, and you can simply type `git push` or `git pull` afterwards.

---

## 2. Discovering Branches (Local vs. Remote)

Before inspecting branches, always synchronize your branch registry with GitHub:

```bash
# Query GitHub for all new, renamed, or deleted branches
git fetch --all --prune
```

### Inspecting Branch Lists:

| Command | What It Shows |
| :--- | :--- |
| `git branch` | Lists only local branches stored on your current machine. |
| `git branch -r` | Lists only remote branches hosted on GitHub (`origin/...`). |
| `git branch -a` | Lists **both** local and remote branches. |

#### Reading the output of `git branch -a`:
```text
* feature/lxnav-hud                      <-- Asterisk indicates your current active branch
  main                                   <-- Local branch
  remotes/origin/main                    <-- GitHub copy of main
  remotes/origin/feature/lxnav-hud       <-- GitHub copy of feature branch
  remotes/origin/canada-expo             <-- Branch on GitHub you haven't checked out yet
```

---

## 3. Switching Branches

### Scenario A: Switching to an existing local branch
```bash
git checkout main
# Or using modern git syntax:
git switch main
```

### Scenario B: Checking out a remote branch for the first time
If someone created `canada-expo` on GitHub and it only appears under `remotes/origin/`:
```bash
git fetch origin
git checkout canada-expo
```
*(Git automatically creates a local branch named `canada-expo` and links it to `origin/canada-expo`)*

### Scenario C: Creating a brand new feature branch
```bash
# Branch off your current work
git checkout -b feature/new-telemetry-dial

# Push and set upstream tracking on GitHub
git push -u origin feature/new-telemetry-dial
```

---

## 4. Pulling the Latest Code

Always follow this 3-step sequence when pulling updates on Windows or Linux:

```bash
# Step 1: Fetch fresh commit history from GitHub without altering local files
git fetch origin

# Step 2: Ensure you are on the target branch
git checkout feature/lxnav-hud

# Step 3: Pull and merge the latest commits into your local files
git pull origin feature/lxnav-hud
```

---

## 5. Pushing Local Work to GitHub

When you make changes to files (e.g. `visualizer/sharkee_hud.html` or `server/server.py`):

```bash
# 1. Check which files were modified
git status

# 2. Stage modified files
git add visualizer/sharkee_hud.html server/server.py
# Or stage all modified tracked files:
git add .

# 3. Commit with a clear, descriptive message
git commit -m "Update PFD styling and sync telemetry widgets"

# 4. Push commits to GitHub
git push origin feature/lxnav-hud
```

---

## 6. Merging Feature Work into `main`

Once testing on `feature/lxnav-hud` is verified and ready for production:

```bash
# 1. Switch to local main
git checkout main

# 2. Ensure main is up to date with GitHub
git pull origin main

# 3. Merge your feature branch into main
git merge feature/lxnav-hud

# 4. Push the merged main branch to GitHub
git push origin main

# 5. Switch back to your feature branch to continue development
git checkout feature/lxnav-hud
```

---

## 7. Multi-OS Workflow (Windows & Linux / WSL)

The Git commands are identical across PowerShell, Command Prompt, and Linux Bash.

### Typical Cross-Platform Routine:

```text
[ Windows Machine (Dev / CAD / Visualizer) ]
   1. Make edits in visualizer or server
   2. git add .
   3. git commit -m "Refine Garmin EIS dials"
   4. git push origin feature/lxnav-hud
                 │
                 ▼
          [ GitHub Remote ]
                 │
                 ▼
[ Linux / WSL Machine (SITL Simulation Host) ]
   1. cd ArdupilotSITL
   2. git fetch origin
   3. git checkout feature/lxnav-hud
   4. git pull origin feature/lxnav-hud
   5. sim_vehicle.py -v ArduPlane -f jsbsim:SharkHawk --out=udp:127.0.0.1:14551
```

---

## 8. Troubleshooting Common Git Scenarios

### Problem 1: Uncommitted changes block switching branches
**Error:** `error: Your local changes to the following files would be overwritten by checkout`
**Solution:**
```bash
# Option A: Stash changes temporarily, switch, and re-apply
git stash
git checkout <target-branch>
git stash pop

# Option B: Discard local changes completely (revert to clean state)
git restore .
git checkout <target-branch>
```

### Problem 2: Port already in use when launching `server.py`
**Error:** `[!] ERROR: Port 8766 is already in use by another Python instance`
**Windows Fix (PowerShell):**
```powershell
Get-Process python | Stop-Process -Force
```
**Linux Fix (Bash):**
```bash
pkill -f "python.*server.py" || fuser -k 8766/tcp
```

### Problem 3: Setting upstream default so you can just type `git pull`
```bash
git branch --set-upstream-to=origin/feature/lxnav-hud feature/lxnav-hud
# Now you can simply type:
git pull
git push
```

