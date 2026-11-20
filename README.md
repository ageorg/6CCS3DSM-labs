# 6CCS3DSM Distributed Systems: Labs, Weeks 1–4

This repository contains the apps used in the lab sessions for the first part of 6CCS3DSM Distributed Systems at King's College London (Weeks 1–4, 2026–27). Each lab is added here in the week it runs.

## How the labs work

Each lab is a small distributed system that runs on your own laptop. A few services send messages to each other over a network, and a web page lets you use the system and see what happens inside it.

- The services and the network are simulated in a single Python program. As on a real network, messages can be lost or delayed.
- The page has three parts: the application as its users see it; the services behind it, each showing only what it knows; and lab tools for investigating, including a timeline of every message.
- Time is simulated and nothing is random, so the same actions always give the same result.
- You do not need to write any code.

## Labs

| Lab | Week | The system | Related topics |
|---|---|---|---|
| [Lab 1](lab1/) | 2 | An online shop with three services: Shop, Stock and Payment | Remote calls between services; failures in a distributed system |
| [Lab 2](lab2/) | 3 | A ticket booking service run from two data centres, London and Dublin | Models of distributed systems; detecting failures |

## Requirements

- Python 3.8 or later. Nothing else needs to be installed.
- A web browser.
- No internet connection is needed once you have the files.

## Getting the code

Either:

- On this page, click **Code**, then **Download ZIP**, and unzip it. The folder is called `6CCS3DSM-labs-main`.
- Or, if you use git, click **Code**, copy the address and run `git clone` with it.

The same files are also on the module's KEATS page.

When a new lab is added, download the ZIP again, or run `git pull` inside the folder.

## Running a lab

Open a terminal, go to the lab's folder and start it:

| System | Commands |
|---|---|
| Windows | `cd lab1` then `py run.py` (or `python run.py`) |
| macOS and Linux | `cd lab1` then `python3 run.py` |

For another lab, use its folder instead of `lab1`. Each lab uses its own port (Lab 1: 8001, Lab 2: 8002); the terminal shows the page address.

The page opens in your browser. Keep the terminal open while you work, and press Ctrl+C in it to stop the lab.

Each lab's own README describes the system in detail and lists solutions to common problems.

## Questions

Ask a TA at the start of your lab session, or post on the module's KEATS page.
