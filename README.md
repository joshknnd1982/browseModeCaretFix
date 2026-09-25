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

There are no settings and no new keys. Once it is installed it just works.

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

## Building it yourself

The add-on is the contents of the `addon` folder, zipped up. There is a script for it:

```
python build.py
```

It writes `dist/browseModeCaretFix-<version>.nvda-addon`, and a `.sha256` file beside it.
Any Python 3 will do; it does not need NVDA, SCons or the add-on template.

## License

GNU General Public License, version 2. See [LICENSE](LICENSE).
