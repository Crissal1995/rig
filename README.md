# RIG - Reddit ID Grabber
## About
Simple script to (try to) grab wanted IDs from Reddit.
Reddit uses 6 characters (back then they were 5) base36 to encode their unique post ids, like the ones in redd.it/iloveu or redd.it/pasta.

It's useless, but it was created trying to grab _italia_ (unfortunately, it didn't happen). It's more of an exercise of programming.

## How to use

``` bash
usage: rig.py [-h] [-p POST_ID] [-c CONFIG] [-w]
```

You can launch the script in two modes, __watch mode__ and __grab mode__.

If you type `-p POST_ID`, you will enter grab mode and the script will try to grab the ID you requested.

If you type `-w` or nothing, you will enter watch mode and just be informed which is the last ID posted on Reddit. You will also be given an ID you can try to grab.
The flag `-w` overrides `-p`.

The flag `-c CONFIG` is used to specify a configuration file (in JSON) to be used. If not specified, it defaults to `config.json`.

### Configuration file
In `config.json` you will need to enter your credentials, the subreddit you want to post in - if blank, it will be used your username page - (it's preferred to leave it blank, because posting in subreddit is subject to flood control), and the 1-to-N clients you can use.

For setupping clients, you need to head to https://www.reddit.com/prefs/apps and create an app (type must be __script__, other fields are insignificant), then take both ID (14 chars long) and Secret (27 chars long).
