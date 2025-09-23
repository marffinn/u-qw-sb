# BROWSANKA - QuakeWorld Server Browser

This is a simple QuakeWorld server browser written in Python with a Tkinter GUI. It allows you to:

* View a list of QuakeWorld servers from a file (`eu-sv.txt`).
* Ping servers to see their current status, including map, players, and ping time.
* Sort servers by various criteria.
* Add and remove servers from a favorites list.
* Connect to a server using your QuakeWorld client.

## Features

* **Server List:** Displays a list of servers with their name, port, ping, map, and player/spectator counts.
* **Favorites:** Maintain a separate list of your favorite servers.
* **Real-time Pinging:** Ping all servers to get up-to-date information.
* **Sorting:** Sort the server list by name, port, ping, map, or player count.
* **Filtering:** Filter servers by a maximum ping threshold.
* **Server Details:** Double-click a server to view detailed information, including a mapshot and a list of players.
* **Connect:** Connect to a server directly from the browser.

## Installation

You can download the latest installer for BROWSANKA from the [GitHub Releases page](https://github.com/marffinn/u-qw-sb/releases).

## Configuration

*   **Server List:** The initial list of servers is read from `eu-sv.txt`. You can edit this file to add or remove servers.
*   **QuakeWorld Client:** The application will attempt to launch `ezquake-gl.exe` to connect to servers. You can change this in the `connect_to_server` function in `main.py`.

## Development / Release

For development and release purposes:

*   **GitHub Token:** The `push_release.bat` script requires a GitHub Personal Access Token (PAT) with appropriate permissions (e.g., `repo` scope) to push commits and tags, and to trigger GitHub Actions workflows. This token should be stored in a `.env` file in the project root, named `GH_TOKEN`.
    Example `.env` file:
    ```
    GH_TOKEN=your_github_token_here
    ```
*   **Release Process:** The `push_release.bat` script automates the release process, including building the executable, creating the installer, committing the installer, and pushing the release tag to GitHub.