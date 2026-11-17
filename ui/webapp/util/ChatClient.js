sap.ui.define([], function () {
  "use strict";

  var DEFAULT_ENDPOINT = "workflow/chat";
  var DEFAULT_CSRF_ENDPOINT = "workflow/";
  var LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]", "::1"];

  /**
   * Error carrying an i18n key (`messageKey`) the controller turns into user text.
   * Keys: errorEmptyPrompt, errorSession, errorForbidden, errorTimeout, errorNetwork,
   * errorGeneric, errorBadResponse.
   */
  function chatError(sMessageKey, iStatus) {
    var oError = new Error(sMessageKey);
    oError.name = "ChatError";
    oError.messageKey = sMessageKey;
    oError.status = iStatus;
    return oError;
  }

  /**
   * Mock mode is on for localhost, or with ?mock=true. ?mock=false forces it off.
   * @param {{search?: string, hostname?: string}} oLocation window.location-like object
   */
  function detectMock(oLocation) {
    var sParam = new URLSearchParams(oLocation.search || "").get("mock");
    if (sParam === "true") {
      return true;
    }
    if (sParam === "false") {
      return false;
    }
    return LOCAL_HOSTS.indexOf(oLocation.hostname) !== -1;
  }

  /**
   * Sends the user's prompt to the workflow endpoint behind the approuter and returns the reply.
   * Contract: POST {endpoint} with {"prompt": "..."} -> 200 {"text": "..."} (other fields ignored).
   */
  class ChatClient {
    /**
     * @param {object} [mOptions]
     * @param {boolean} [mOptions.mock] force mock mode on/off (default: detectMock)
     * @param {string} [mOptions.endpoint] POST url (relative, so it works under the versioned HTML5 path)
     * @param {string} [mOptions.csrfEndpoint] GET url used to fetch the CSRF token
     * @param {number} [mOptions.timeoutMs] request timeout, default 30000
     * @param {number} [mOptions.mockDelayMs] simulated latency, default 700
     * @param {Function} [mOptions.fetch] fetch implementation (tests)
     * @param {object} [mOptions.location] window.location-like object (tests)
     */
    constructor(mOptions) {
      var mOpts = mOptions || {};
      this._endpoint = mOpts.endpoint || DEFAULT_ENDPOINT;
      this._csrfEndpoint = mOpts.csrfEndpoint || DEFAULT_CSRF_ENDPOINT;
      this._timeoutMs = mOpts.timeoutMs !== undefined ? mOpts.timeoutMs : 30000;
      this._mockDelayMs = mOpts.mockDelayMs !== undefined ? mOpts.mockDelayMs : 700;
      this._fetch = mOpts.fetch || function () {
        return window.fetch.apply(window, arguments);
      };
      this._mock = typeof mOpts.mock === "boolean"
        ? mOpts.mock
        : detectMock(mOpts.location || window.location);
      this._csrfToken = null;
    }

    isMock() {
      return this._mock;
    }

    /**
     * @param {string} sPrompt user question
     * @returns {Promise<{text: string}>}
     * @throws ChatError (see chatError) via rejection
     */
    async send(sPrompt) {
      if (typeof sPrompt !== "string" || !sPrompt.trim()) {
        throw chatError("errorEmptyPrompt");
      }
      var sClean = sPrompt.trim();
      if (this._mock) {
        return this._mockReply(sClean);
      }

      var oResponse = await this._post(sClean);
      if (oResponse.status === 403) {
        // Possibly a stale CSRF token: refresh once and retry before reporting "forbidden".
        this._csrfToken = null;
        oResponse = await this._post(sClean);
      }
      return this._readReply(oResponse);
    }

    _mockReply(sPrompt) {
      var iDelay = this._mockDelayMs;
      return new Promise(function (resolve, reject) {
        setTimeout(function () {
          if (/\berror\b/i.test(sPrompt)) {
            reject(chatError("errorGeneric", 500));
            return;
          }
          resolve({
            text: "Mock reply: the workflow is not connected yet. You asked: \"" + sPrompt + "\""
          });
        }, iDelay);
      });
    }

    async _post(sPrompt) {
      if (!this._csrfToken) {
        await this._fetchCsrfToken();
      }
      var mHeaders = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        // Makes the approuter answer 401 instead of redirecting an expired session to the IdP.
        "X-Requested-With": "XMLHttpRequest"
      };
      if (this._csrfToken) {
        mHeaders["X-CSRF-Token"] = this._csrfToken;
      }
      return this._request(this._endpoint, {
        method: "POST",
        headers: mHeaders,
        body: JSON.stringify({ prompt: sPrompt })
      });
    }

    async _fetchCsrfToken() {
      var oResponse = await this._request(this._csrfEndpoint, {
        method: "GET",
        headers: { "X-CSRF-Token": "Fetch", "X-Requested-With": "XMLHttpRequest" }
      });
      this._throwForAuth(oResponse);
      this._csrfToken = oResponse.headers.get("x-csrf-token") || null;
    }

    async _request(sUrl, mInit) {
      var oController = new AbortController();
      var iTimer = setTimeout(function () {
        oController.abort();
      }, this._timeoutMs);
      try {
        return await this._fetch(sUrl, Object.assign({
          credentials: "same-origin",
          redirect: "manual",
          signal: oController.signal
        }, mInit));
      } catch (oError) {
        throw chatError(oError && oError.name === "AbortError" ? "errorTimeout" : "errorNetwork");
      } finally {
        clearTimeout(iTimer);
      }
    }

    _throwForAuth(oResponse) {
      if (oResponse.type === "opaqueredirect" || oResponse.status === 401) {
        throw chatError("errorSession", 401);
      }
      if (oResponse.status === 403) {
        throw chatError("errorForbidden", 403);
      }
    }

    async _readReply(oResponse) {
      this._throwForAuth(oResponse);
      if (!oResponse.ok) {
        throw chatError("errorGeneric", oResponse.status);
      }
      var oBody;
      try {
        oBody = await oResponse.json();
      } catch (oError) {
        throw chatError("errorBadResponse", oResponse.status);
      }
      if (!oBody || typeof oBody.text !== "string" || !oBody.text) {
        throw chatError("errorBadResponse", oResponse.status);
      }
      return { text: oBody.text };
    }
  }

  ChatClient.detectMock = detectMock;
  return ChatClient;
});
