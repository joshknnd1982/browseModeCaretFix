# -*- coding: utf-8 -*-
"""Browse Mode Caret Fix (3.0.23).

Restores the browse-mode caret after Alt+Left in Microsoft Edge, including
single-page applications whose virtual buffer is not rebuilt by navigation.
"""

import time
from urllib.parse import urlsplit, urlunsplit

import api
import browseMode
import controlTypes
import core
import globalPluginHandler
import inputCore
import textInfos
from logHandler import log
from NVDAObjects import NVDAObject

ADDON_LOG_PREFIX = "Browse Mode Caret Fix"

_FINGERPRINT_PROBE_LINES = 12
_MAX_SAVED_POSITIONS_PER_DOCUMENT = 20
_NAVIGATION_TIMEOUT_SECONDS = 5.0
_FAST_POLL_WINDOW_SECONDS = 3.0
_FAST_POLL_MS = 50
_SLOW_POLL_MS = 200
_FOCUS_CACHE_REFRESH_AFTER_SECONDS = 0.20
_FOCUS_CACHE_REFRESH_INTERVAL_SECONDS = 0.20

# Normalized document ID -> activation positions, newest last.
_savedPositionStacks = {}
# Chronological source-document keys for link activations. The newest one is
# the exact document a Back operation should return to.
_backTargetKeys = []
_pendingNavigation = None
_navigationSerial = 0
_pendingRedditOpen = None
_redditOpenSerial = 0

_originalActivatePosition = None


def _isEdgeFocus():
	try:
		obj = api.getFocusObject()
		return bool(obj and obj.appModule and obj.appModule.appName == "msedge")
	except Exception:
		return False


def _getNavigationDirection(gesture):
	"""Return -1 for Alt+Left, 1 for Alt+Right, or 0 otherwise."""
	try:
		identifiers = gesture.normalizedIdentifiers
	except Exception:
		identifiers = ()
	for identifier in identifiers or ():
		try:
			keys = identifier.casefold().split(":", 1)[1]
		except (AttributeError, IndexError):
			continue
		parts = set(keys.split("+"))
		if parts == {"alt", "leftarrow"}:
			return -1
		if parts == {"alt", "rightarrow"}:
			return 1
	return 0


def _getRawDocId(treeInterceptor):
	try:
		return treeInterceptor.documentConstantIdentifier
	except Exception:
		return None


def _normalizeDocId(docId):
	"""Make fragment-only history entries share one caret-position key."""
	if not isinstance(docId, str) or not docId.strip():
		return None
	docId = docId.strip()
	try:
		parts = urlsplit(docId)
		if parts.scheme and parts.netloc:
			return urlunsplit((
				parts.scheme.casefold(),
				parts.netloc.casefold(),
				parts.path,
				parts.query,
				"",
			))
	except (TypeError, ValueError):
		pass
	return docId.split("#", 1)[0]


def _getDocKey(treeInterceptor):
	return _normalizeDocId(_getRawDocId(treeInterceptor))


def _isRedditPostUrl(docId):
	if not isinstance(docId, str):
		return False
	try:
		parts = urlsplit(docId)
		host = parts.netloc.casefold().split(":", 1)[0]
		pathParts = [part.casefold() for part in parts.path.split("/") if part]
		return (
			(host == "reddit.com" or host.endswith(".reddit.com"))
			and "comments" in pathParts
		)
	except (TypeError, ValueError):
		return False


def _getLineFingerprint(info):
	try:
		lineInfo = info.copy()
		lineInfo.expand(textInfos.UNIT_LINE)
		return lineInfo.text.strip()
	except Exception:
		return ""


def _scheduleNextAttempt(callback, pending):
	"""Keep only one lightweight timer outstanding for this operation."""
	now = time.monotonic()
	remaining = pending["deadline"] - now
	if remaining <= 0:
		return False
	delay = (
		_FAST_POLL_MS
		if now - pending["started"] < _FAST_POLL_WINDOW_SECONDS
		else _SLOW_POLL_MS
	)
	delay = min(delay, max(1, int(remaining * 1000)))
	core.callLater(delay, callback, pending["token"])
	return True


def _isLinkPosition(info):
	"""Avoid filling the history stack when buttons and form controls activate."""
	try:
		obj = info.NVDAObjectAtStart
		for _ in range(6):
			if obj is None:
				break
			if obj.role == controlTypes.Role.LINK:
				return True
			obj = obj.parent
	except Exception:
		pass

	try:
		probe = info.copy()
		probe.expand(textInfos.UNIT_CHARACTER)
		for item in probe.getTextWithFields():
			if (
				isinstance(item, textInfos.FieldCommand)
				and item.command == "controlStart"
				and item.field
				and item.field.get("role") == controlTypes.Role.LINK
			):
				return True
	except Exception:
		pass
	return False


def _saveActivationPosition(treeInterceptor, info, docKey=None):
	if docKey is None:
		docKey = _getDocKey(treeInterceptor)
	if docKey is None:
		log.debug("%s: skipped save because document ID is unavailable" % ADDON_LOG_PREFIX)
		return
	try:
		entry = {
			"bookmark": info.bookmark,
			"fingerprint": _getLineFingerprint(info),
		}
	except Exception:
		log.debug("%s: could not capture activation position" % ADDON_LOG_PREFIX, exc_info=True)
		return

	stack = _savedPositionStacks.setdefault(docKey, [])
	stack.append(entry)
	_backTargetKeys.append(docKey)
	if len(stack) > _MAX_SAVED_POSITIONS_PER_DOCUMENT:
		del stack[:-_MAX_SAVED_POSITIONS_PER_DOCUMENT]
	if len(_backTargetKeys) > 100:
		del _backTargetKeys[:-100]
	log.debug(
		"%s: saved link activation docKey=%r stackDepth=%d"
		% (ADDON_LOG_PREFIX, docKey, len(stack))
	)


def _attemptPendingRedditOpen(token):
	global _pendingRedditOpen
	pending = _pendingRedditOpen
	if not pending or pending.get("token") != token:
		return
	timedOut = time.monotonic() >= pending["deadline"]
	if not _isEdgeFocus():
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return
	try:
		treeInterceptor = api.getFocusObject().treeInterceptor
		if not isinstance(treeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor):
			raise AttributeError("focus has no browse-mode treeInterceptor")
	except Exception:
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return

	rawDocId = _getRawDocId(treeInterceptor)
	if rawDocId == pending.get("startRawDocId") or not _isRedditPostUrl(rawDocId):
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return
	try:
		first = treeInterceptor.makeTextInfo(textInfos.POSITION_FIRST)
		treeInterceptor.selection = first
		treeInterceptor.rootNVDAObject.setFocus()
	except Exception:
		log.debug("%s: Reddit top-position attempt failed; will retry" % ADDON_LOG_PREFIX, exc_info=True)
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return
	log.debug("%s: moved newly opened Reddit post to document top" % ADDON_LOG_PREFIX)
	_pendingRedditOpen = None


def _trackRedditPostOpen(startRawDocId):
	global _pendingRedditOpen, _redditOpenSerial
	try:
		parts = urlsplit(startRawDocId)
		host = parts.netloc.casefold().split(":", 1)[0]
		if host != "reddit.com" and not host.endswith(".reddit.com"):
			return
	except (AttributeError, TypeError, ValueError):
		return
	_redditOpenSerial += 1
	token = _redditOpenSerial
	now = time.monotonic()
	_pendingRedditOpen = {
		"token": token,
		"startRawDocId": startRawDocId,
		"started": now,
		"deadline": now + _NAVIGATION_TIMEOUT_SECONDS,
	}
	core.callLater(_FAST_POLL_MS, _attemptPendingRedditOpen, token)


def _patched_activatePosition(treeInterceptor, *args, **kwargs):
	"""Save only genuine link activations, then let NVDA activate normally."""
	info = None
	startRawDocId = _getRawDocId(treeInterceptor)
	startDocKey = _normalizeDocId(startRawDocId)
	try:
		candidate = treeInterceptor.selection.copy()
		if _isLinkPosition(candidate):
			info = candidate
	except Exception:
		log.debug("%s: link-position check failed" % ADDON_LOG_PREFIX, exc_info=True)

	result = _originalActivatePosition(treeInterceptor, *args, **kwargs)
	if info is not None:
		_saveActivationPosition(treeInterceptor, info, startDocKey)
		_trackRedditPostOpen(startRawDocId)
	return result


def _findFingerprintNearBookmark(info, fingerprint):
	if not fingerprint or _getLineFingerprint(info) == fingerprint:
		return info
	for distance in range(1, _FINGERPRINT_PROBE_LINES + 1):
		for direction in (-1, 1):
			probe = info.copy()
			try:
				if not probe.move(textInfos.UNIT_LINE, direction * distance):
					continue
			except Exception:
				continue
			if _getLineFingerprint(probe) == fingerprint:
				log.debug(
					"%s: fingerprint matched %d line(s) from bookmark"
					% (ADDON_LOG_PREFIX, direction * distance)
				)
				return probe
	log.debug("%s: fingerprint not found near bookmark; using bookmark" % ADDON_LOG_PREFIX)
	return info


def _restoreForTreeInterceptor(treeInterceptor):
	docKey = _getDocKey(treeInterceptor)
	stack = _savedPositionStacks.get(docKey) or []
	log.debug(
		"%s: restore lookup docKey=%r stackDepth=%d"
		% (ADDON_LOG_PREFIX, docKey, len(stack))
	)
	if not stack:
		return False

	# Peek first so a transient virtual-buffer failure doesn't destroy the
	# only saved position. Pop only after the selection was applied.
	entry = stack[-1]
	try:
		info = treeInterceptor.makeTextInfo(entry["bookmark"])
		info = _findFingerprintNearBookmark(info, entry.get("fingerprint"))
		treeInterceptor.selection = info
		treeInterceptor.rootNVDAObject.setFocus()
	except Exception:
		log.debug("%s: restore attempt failed; will retry" % ADDON_LOG_PREFIX, exc_info=True)
		return False

	stack.pop()
	if not stack:
		_savedPositionStacks.pop(docKey, None)
	log.debug("%s: restored saved position" % ADDON_LOG_PREFIX)
	return True


def _refreshNvdaFocusCache(pending):
	"""Refresh NVDA's cached focus without physically moving Windows focus."""
	now = time.monotonic()
	if now - pending["started"] < _FOCUS_CACHE_REFRESH_AFTER_SECONDS:
		return None
	if now - pending.get("lastCacheRefresh", 0.0) < _FOCUS_CACHE_REFRESH_INTERVAL_SECONDS:
		return None
	pending["lastCacheRefresh"] = now
	try:
		freshFocus = NVDAObject.objectWithFocus()
		if freshFocus is None or not api.setFocusObject(freshFocus):
			return None
		treeInterceptor = getattr(freshFocus, "treeInterceptor", None)
		log.debug(
			"%s: refreshed NVDA focus cache; document key is %r"
			% (ADDON_LOG_PREFIX, _getDocKey(treeInterceptor))
		)
		return treeInterceptor
	except Exception:
		log.debug("%s: NVDA focus-cache refresh failed" % ADDON_LOG_PREFIX, exc_info=True)
		return None


def _attemptPendingNavigation(token):
	global _pendingNavigation
	pending = _pendingNavigation
	if not pending or pending.get("token") != token or pending.get("restoring"):
		return
	timedOut = time.monotonic() >= pending["deadline"]
	if not _isEdgeFocus():
		if timedOut:
			_pendingNavigation = None
		else:
			_scheduleNextAttempt(_attemptPendingNavigation, pending)
		return

	try:
		treeInterceptor = api.getFocusObject().treeInterceptor
		if not isinstance(treeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor):
			raise AttributeError("focus has no browse-mode treeInterceptor")
	except Exception:
		if timedOut:
			log.debug("%s: navigation ended without a browse-mode document" % ADDON_LOG_PREFIX)
			_pendingNavigation = None
		else:
			_scheduleNextAttempt(_attemptPendingNavigation, pending)
		return

	targetDocKey = pending.get("targetDocKey")
	currentDocKey = _getDocKey(treeInterceptor)
	if currentDocKey != targetDocKey:
		refreshedTreeInterceptor = _refreshNvdaFocusCache(pending)
		if isinstance(refreshedTreeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor):
			treeInterceptor = refreshedTreeInterceptor
			currentDocKey = _getDocKey(treeInterceptor)

	elapsed = time.monotonic() - pending["started"]
	# Restore only in the exact source document recorded at link activation.
	navigationReady = currentDocKey == targetDocKey and elapsed >= 0.15
	if not navigationReady:
		if timedOut:
			log.debug("%s: destination buffer did not appear before timeout" % ADDON_LOG_PREFIX)
			_pendingNavigation = None
		else:
			_scheduleNextAttempt(_attemptPendingNavigation, pending)
		return

	pending["restoring"] = True
	try:
		restored = _restoreForTreeInterceptor(treeInterceptor)
	finally:
		pending["restoring"] = False
	if restored:
		if _backTargetKeys and _backTargetKeys[-1] == targetDocKey:
			_backTargetKeys.pop()
		_pendingNavigation = None
	elif timedOut:
		log.debug("%s: no saved position became available after navigation" % ADDON_LOG_PREFIX)
		_pendingNavigation = None
	else:
		_scheduleNextAttempt(_attemptPendingNavigation, pending)


def _onDecideExecuteGesture(gesture):
	"""Observe Back/Forward via NVDA's extension point without blocking it."""
	global _navigationSerial, _pendingNavigation, _pendingRedditOpen
	try:
		direction = _getNavigationDirection(gesture)
		if not direction or not _isEdgeFocus():
			return True
		_pendingRedditOpen = None
		if direction > 0:
			return True
		if not _backTargetKeys:
			log.debug("%s: saw Back, but no saved link activation exists" % ADDON_LOG_PREFIX)
			return True
		_navigationSerial += 1
		token = _navigationSerial
		now = time.monotonic()
		_pendingNavigation = {
			"token": token,
			"direction": direction,
			"started": now,
			"deadline": now + _NAVIGATION_TIMEOUT_SECONDS,
			"targetDocKey": _backTargetKeys[-1],
			"lastCacheRefresh": 0.0,
			"restoring": False,
		}
		log.debug(
			"%s: saw Back navigation gesture; target document is %r"
			% (ADDON_LOG_PREFIX, _backTargetKeys[-1])
		)
		core.callLater(_FAST_POLL_MS, _attemptPendingNavigation, token)
	except Exception:
		# A gesture observer must never interfere with NVDA input.
		log.debug("%s: navigation gesture observer failed" % ADDON_LOG_PREFIX, exc_info=True)
	return True


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		global _originalActivatePosition

		_originalActivatePosition = browseMode.BrowseModeDocumentTreeInterceptor._activatePosition

		browseMode.BrowseModeDocumentTreeInterceptor._activatePosition = _patched_activatePosition
		inputCore.decide_executeGesture.register(_onDecideExecuteGesture)

	def terminate(self):
		global _pendingNavigation, _pendingRedditOpen
		_pendingNavigation = None
		_pendingRedditOpen = None
		try:
			inputCore.decide_executeGesture.unregister(_onDecideExecuteGesture)
		except Exception:
			pass
		if _originalActivatePosition is not None:
			browseMode.BrowseModeDocumentTreeInterceptor._activatePosition = _originalActivatePosition
		super(GlobalPlugin, self).terminate()
