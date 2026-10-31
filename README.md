# oonDownloader

![oonDownloader](screenshot.png)

A simple desktop app for downloading video and audio. Built with Python and customtkinter. 
Using yt-dlp and ffmpeg under the hood, it works with YouTube and all other sites yt-dlp supports.

## Features
- Download as **mp4**  or **mp3**
- Simple download statistics
- Downloads and updates yt-dlp by itself from within the app ("Update yt-dlp")
- Single video links only (playlist and channel links are not supported)
- Supported sites: see the [yt-dlp supported sites list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## Requirements
- Windows
- Python 3.10 or newer
- [ffmpeg](https://ffmpeg.org/download.html) installed and added to PATH

## Installation
1. Clone the repository:
   git clone https://github.com/oppositeofnice/oonDownloader.git
   cd oonDownloader
2. Install the dependencies:
   pip install -r requirements.txt
3. Run the app:
   python oonDownloader.py

On first use the app downloads yt-dlp.exe automatically. The download
history and yt-dlp.exe are stored in `%APPDATA%\oonDownloader`.

## Disclaimer
This tool is for personal use. Please respect the terms of service of the
websites you download from and the rights of content owners.
