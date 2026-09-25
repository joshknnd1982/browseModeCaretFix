"""Packs addon/ into a .nvda-addon file.

An NVDA add-on is just a zip of the addon directory's contents, so this avoids
needing SCons or the add-on template for a package this small. Run with any
Python 3: ``python build.py``

Writes dist/<name>-<version>.nvda-addon and a matching .sha256 file. The name
and version come from addon/manifest.ini.
"""

import hashlib
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "addon")
DIST = os.path.join(HERE, "dist")
MANIFEST = os.path.join(SOURCE, "manifest.ini")

#: A fixed time for every file in the package, so the same source always builds the same bytes.
ZIP_TIME = (2026, 1, 1, 0, 0, 0)
#: Never ship these.
EXCLUDE_DIRS = {"__pycache__", ".git"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".pyd")


def readManifestValue(key):
	with open(MANIFEST, encoding="utf-8") as f:
		match = re.search(r"^%s\s*=\s*(.+)$" % re.escape(key), f.read(), re.MULTILINE)
	if not match:
		raise RuntimeError("%s missing from manifest.ini" % key)
	return match.group(1).strip().strip('"')


def packageFiles():
	files = []
	for root, dirs, names in os.walk(SOURCE):
		dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
		for filename in sorted(names):
			if filename.endswith(EXCLUDE_SUFFIXES):
				continue
			path = os.path.join(root, filename)
			# Forward slashes, relative to addon/, or NVDA will not find anything.
			files.append((path, os.path.relpath(path, SOURCE).replace(os.sep, "/")))
	return files


def build():
	name = readManifestValue("name")
	version = readManifestValue("version")
	os.makedirs(DIST, exist_ok=True)
	fileName = "%s-%s.nvda-addon" % (name, version)
	target = os.path.join(DIST, fileName)

	files = packageFiles()
	with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
		for path, arcname in files:
			info = zipfile.ZipInfo(arcname, ZIP_TIME)
			info.compress_type = zipfile.ZIP_DEFLATED
			info.external_attr = 0o644 << 16
			with open(path, "rb") as f:
				zf.writestr(info, f.read())

	with open(target, "rb") as f:
		digest = hashlib.sha256(f.read()).hexdigest()
	with open(target + ".sha256", "w", encoding="ascii", newline="\n") as f:
		f.write("%s  %s\n" % (digest, fileName))
	print("Wrote %s (%d files)" % (target, len(files)))
	print("SHA-256 %s" % digest)
	return target


if __name__ == "__main__":
	build()
