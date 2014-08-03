# P4Gutter
----------

Sublime Text 3 plugin to display Perforce diffs in the gutter. Displays additions, deletions, and modifications.


### Looks like
![screenshot](screenshot.png)


### Installation
Look for the *P4Gutter* package in Sublime [Package Control](https://sublime.wbond.net/).


### Setup
* You'll need the Perforce command line client ([Perforce Downloads](http://www.perforce.com/downloads/Perforce/Customer))
* Edit settings, from Preferences > Package Settings > P4Gutter > Settings
	* Set Perforce **binary path**, **server**, **user**, and **workspace**.
* Optionally for workspaces, create a "**.p4_workspace**" file in your workspace root directory; with the workspace name inside of the file.


### Usage
The gutter is updated on file *open* and *save* events.


### License
MIT Licensed


### Thanks
Icons from [GitGutter](https://github.com/jisaacks/GitGutter) by [JD Isaacks](https://github.com/jisaacks).