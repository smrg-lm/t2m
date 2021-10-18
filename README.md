Repository content
------------------

```
config.yaml       # runtime configurable parameters
freesound_v2.yaml # blueprint to zip freesound login data
README.md         # this readme
requirements.txt  # python required packages
t2m.py            # the app script
twitter_v1.yaml   # blueprint to zip twitter login data
```

After install and setup this directory will contain:

```
credentials.zip   # a zip file with passowrd
t2mvenv           # a python virtual environmnet folder
```


Install
-------

This is a command line application that has to be installed and run manually.
`python`, `git` and `ffmpeg` commands must be accessible from a terminal.

1. Install SuperCollider: https://supercollider.github.io/download

   Run the SuperCollider's IDE and boot the server at least once to enable network
   permissions for the server and quit the IDE. The IDE is not needed later.

2. Install ffmpeg command.

   On Windows 10:

   - Download: https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2021-10-14-12-22/ffmpeg-N-104348-gbb10f8d802-win64-gpl.zip
   - Unzip the folder to program files and set the contained bin directory in
     the PATH environment variable.
   - Check ffmpeg command is available from PowerShell.

3. Install git: https://git-scm.com/downloads

4. Install Python 3.8+ in your platform: https://www.python.org/downloads

5. Clone t2m repo

    ```
    git clone https://github.com/smrg-lm/t2m
    ```

    and move to the t2m created directory.

5. Create a virtual env within t2m directory

    ```
    python -m venv t2mvenv
    ```

    To activate it on Linux or Mac:

    ```bash
    source t2mvenv/bin/activate
    ```

    To activate it on Windows 10:

    ```PowerShell
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
    t2mvenv\Scripts\Activate.ps1
    ```

    Upgrade pip:

    ```
    python pip install pip --upgrade
    ```

6. Install required packages with t2mvenv activated

    ```
    python -m pip install -r requirements.txt
    ```

    Install spacy en model afterwards

    ```
    python -m spacy download en_core_web_sm
    ```


Credentials
-----------

The program needs a standard (e.g. Info-ZIP) password protected zip file
containing only two files: freesounds_v2.yaml and twitter_v1.yaml that in turn
contain the keys and secrets to use the app. Blueprints of these files are
provided.

Info-ZIP on Linux will compress and encrypt the files with this command:

```bash
zip -e credentials.zip freesound_v2.yaml twitter_v1.yaml
```


Configuration
-------------

A few run time parameters can be configured using the `config.yaml` file.

```yaml
hashtag: '#t2mtest'            # a str with the hastag or search query for Twitter API
select: [ADJ, NOUN]            # a list of word types (without quotes) for spacy analysis
filter: 'duration:[15 TO 30]'  # Freesound API search filters
search_wait_time: 15           # a number as wait time between searches (also initial wait time)
tweet_dur: 40                  # a number as the duration of shown tweets if sounds were found
credentials: 'credentials.zip' # the filename of the credentials file
```


Run
---

1. cd to the t2m directory.

2. Activate t2mvenv

    Linux or Mac:

    ```bash
    source t2mvenv/bin/activate
    ```

    Windows 10:

    ```PowerShell
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
    t2mvenv\Scripts\Activate.ps1
    ```

3. Run the script

    ```
    python t2m.py
    ```

    The password for credentials.zip file will be prompted in the terminal
    then the app creates a window that can be placed in another screen for
    projection. The window has two keyboard actions, `F` to toggle full screen
    and `Esc` to exit the app. All runtime log information will post in the
    running terminal for monitoring.


Links
-----

- https://www.python.org/downloads

- https://git-scm.com/downloads

- https://www.ffmpeg.org/download.html

- https://supercollider.github.io/download

- http://infozip.sourceforge.net or any other standard zip utility

- https://docs.tweepy.org/en/stable/api.html#API.search
- https://developer.twitter.com/en/docs/twitter-api/v1/tweets/search/api-reference/get-search-tweets

- https://github.com/mtg/freesound-python
- https://freesound.org/docs/api/
- https://freesound.org/docs/api/resources_apiv2.html

- http://compmus.ime.usp.br/sbcm/2017/papers/sbcm-2017-32.pdf
- https://vimeo.com/242598844
