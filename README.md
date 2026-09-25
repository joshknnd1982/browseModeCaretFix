# Browse Mode Caret Fix

An NVDA add-on that puts you back on the link you came from when you go back a page in
Microsoft Edge.

You are reading a page in browse mode. You press Enter on a link, read the page it opens,
then press alt+left arrow to go back. NVDA should drop you back on that link, but in Edge it
often puts you at the top of the page instead, and you have to find your place all over
again. This add-on remembers the link you pressed and puts the browse mode cursor back on it.

Tested with NVDA 2026.2.

## Get it

Download the `.nvda-addon` file from the [Releases](../../releases/latest) page and open it.
Then restart NVDA.

Once it is installed it just works. Its only settings are for updates, below.

## What it does

**Back puts you on the link.** When you press Enter on a link, the add-on notes where it
was. When you press alt+left arrow in Edge and that page comes back, the cursor lands on the
link again.

**Pages that change underneath you.** If the page has shifted a little since you left, and
the link is no longer exactly where it was, the add-on looks a dozen lines either way for the
same line of text and puts you there.

**Web apps as well as ordinary pages.** Some sites never really load a new page when you
follow a link; they swap the content in place, so NVDA does not notice that you have gone
back. The add-on checks for that and still puts you back where you were.

**Going back more than once.** Follow a link, then another, then another, and each
alt+left arrow puts you on the link you pressed on that page. It remembers the last 20 links
on each page.

**Only links count.** Pressing a button or ticking a check box does not change where back
takes you.

**Reddit posts start at the top.** When you open a post from Reddit, the cursor starts at
the top of the post instead of wherever Reddit left it.

Alt+right arrow, going forward, is left alone. Nothing changes in any browser other than
Edge.

## Updates

The add-on checks for updates. Once a day, a little after NVDA starts, the add-on asks its GitHub repository, [github.com/joshknnd1982/browseModeCaretFix](https://github.com/joshknnd1982/browseModeCaretFix), whether a newer version has been released, and says nothing unless there is one. When there is, a dialog shows what's new in a box you can read line by line, and offers to download and install it. The download must match the release's SHA-256 checksum. Then NVDA asks you to confirm the installation and offers to restart. Your settings are kept.

To check yourself, open the NVDA menu, choose **Tools**, then **Check for add-on updates**, and choose **Browse Mode Caret Fix...**. Or press **Check for updates now** in the add-on's settings: NVDA menu, Preferences, Settings, **Browse Mode Caret Fix**. You can also assign a gesture to **Checks for Browse Mode Caret Fix updates** in NVDA's Input Gestures dialog, under **Browse Mode Caret Fix**. To stop the daily check, clear **Check for Browse Mode Caret Fix updates automatically** in the same settings panel.

## Building it yourself

The add-on is the contents of the `addon` folder, zipped up. There is a script for it:

```
python build.py
```

It writes `dist/browseModeCaretFix-<version>.nvda-addon`, and a `.sha256` file beside it.
Upload both to the GitHub release, tagged `v<version>`: the update check reads the tag and
checks the download against the `.sha256` file.

`addon/globalPlugins/browseModeCaretFix/updater.py` is the update check, shared by all of
joshknnd1982's add-ons; keep it identical to theirs.
Any Python 3 will do; it does not need NVDA, SCons or the add-on template.

## License

GNU General Public License, version 2. See [LICENSE](LICENSE).
