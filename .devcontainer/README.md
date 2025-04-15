# Extended Contributing Docs 📝

Nilakandi use devcontainers pretty heavely. By using devcontainers we can ensure our code can be run on the deployment server as it can run in the locals. Please do refer to `.devcontainer/python/devcontainer.json` to see the full setups.

## Setting Up Dev Environment 🏕️

Please do make sure that you have `docker` installed on your machine.

> Guide bellow is for VSCode User

1. Install Remote Devlopment Extension pack: [VS Marketplace Link](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack)
2. Open command Palette: <kbd>f1</kbd> or <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>p</kbd>
3. Search for `Dev Containers: Build and open in containers` and select
4. Wait until the process finished
5. Open a new terminal: <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>`</kbd>
6. Type `poetry env info --executable` and copy the output
7. Open command Palette: <kbd>f1</kbd> or <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>p</kbd>
8. Search for: `Python: Select Intepreter` and select
9. Select `Enter interpreter path...` and Paste the value
10. Profit 💵


## Dev Containers Spec ⚙️

Though dev containers can be used extensively, We use VSCode as our main text editor. You are free to add another devcontainers to your preferences if neccesary.

__Specs__:

* Template: [mcr.microsoft.com/devcontainers/python:1-3.12-bullseye](https://mcr.microsoft.com/en-us/artifact/mar/devcontainers/python/about)
* Features: 
    * Poetry Integration: [ghcr.io/devcontainers-extra/features/poetry:2](https://github.com/devcontainers-extra/features/tree/main/src/poetry)
    * Github Integration [ghcr.io/joshuanianji/devcontainer-features/github-cli-persistence:1](https://github.com/joshuanianji/devcontainer-features/tree/main/src/github-cli-persistence)
* Extentsions:
    * Language Server: ms-python.python
    * Import Sort: ms-python.isort
    * Formatter: ms-python.black-formatter
    * Django-HTML Linter: monosans.djlint
    * Python Linter: charliermarsh.ruff
    * Django Ext.: batisteo.vscode-django
    * Easier Python Docs: njpwerner.autodocstring
* Recommendation:
    * Extension:
        * Spell checker: streetsidesoftware.code-spell-checker
        * TOML Linter: tamasfe.even-better-toml
        * Colorful Indent: oderwat.indent-rainbow
        * To Do Managers: Gruntfuggly.todo-tree
