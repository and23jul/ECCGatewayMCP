sap.ui.define([
  "aps/pco/eccgatewaychat/util/ChatClient"
], function (ChatClient) {
  "use strict";

  /** Minimal fetch Response stand-in. */
  function response(mOpts) {
    var mHeaders = mOpts.headers || {};
    return {
      status: mOpts.status === undefined ? 200 : mOpts.status,
      ok: (mOpts.status === undefined ? 200 : mOpts.status) < 400,
      type: mOpts.type || "basic",
      headers: {
        get: function (sName) {
          return mHeaders[sName.toLowerCase()] || null;
        }
      },
      json: function () {
        if (mOpts.badJson) {
          return Promise.reject(new SyntaxError("Unexpected token"));
        }
        return Promise.resolve(mOpts.body);
      }
    };
  }

  /** fetch stub that serves queued responses in order and records every call. */
  function fetchStub(aResponses) {
    var aQueue = aResponses.slice();
    var fn = function (sUrl, mInit) {
      fn.calls.push({ url: sUrl, init: mInit });
      var oNext = aQueue.shift();
      if (oNext instanceof Error) {
        return Promise.reject(oNext);
      }
      return Promise.resolve(oNext);
    };
    fn.calls = [];
    return fn;
  }

  function realClient(aResponses, mExtra) {
    var fetch = fetchStub(aResponses);
    var client = new ChatClient(Object.assign({ mock: false, fetch: fetch }, mExtra));
    return { client: client, fetch: fetch };
  }

  function csrfOk(sToken) {
    return response({ headers: { "x-csrf-token": sToken || "tok-1" } });
  }

  /** Awaits a promise that must reject with a ChatError carrying `sKey` (works on old QUnit, which has no assert.rejects). */
  async function rejectsWith(assert, oPromise, sKey) {
    try {
      await oPromise;
    } catch (oError) {
      assert.strictEqual(oError.messageKey, sKey, "rejects with " + sKey);
      return;
    }
    assert.ok(false, "expected a rejection with " + sKey);
  }

  QUnit.module("ChatClient.detectMock");

  QUnit.test("localhost and 127.0.0.1 default to mock", function (assert) {
    assert.strictEqual(ChatClient.detectMock({ hostname: "localhost", search: "" }), true);
    assert.strictEqual(ChatClient.detectMock({ hostname: "127.0.0.1", search: "" }), true);
  });

  QUnit.test("a deployed host defaults to the real endpoint", function (assert) {
    assert.strictEqual(ChatClient.detectMock({
      hostname: "ecc-gateway-chat.cfapps.eu10-004.hana.ondemand.com", search: ""
    }), false);
  });

  QUnit.test("?mock=true forces mock on, ?mock=false forces it off", function (assert) {
    assert.strictEqual(ChatClient.detectMock({ hostname: "app.example", search: "?mock=true" }), true);
    assert.strictEqual(ChatClient.detectMock({ hostname: "localhost", search: "?mock=false" }), false);
  });

  QUnit.module("ChatClient.send (mock)");

  QUnit.test("returns a canned reply that echoes the prompt", async function (assert) {
    var client = new ChatClient({ mock: true, mockDelayMs: 0 });
    var reply = await client.send("  hello  ");
    assert.ok(reply.text.indexOf("\"hello\"") !== -1, "prompt is trimmed and echoed");
  });

  QUnit.test("a prompt containing 'error' simulates a failure", async function (assert) {
    var client = new ChatClient({ mock: true, mockDelayMs: 0 });
    await rejectsWith(assert, client.send("please error out"), "errorGeneric");
  });

  QUnit.test("an empty prompt is rejected before anything is sent", async function (assert) {
    var ctx = realClient([]);
    await rejectsWith(assert, ctx.client.send("   "), "errorEmptyPrompt");
    assert.strictEqual(ctx.fetch.calls.length, 0, "no request made");
  });

  QUnit.module("ChatClient.send (real endpoint)");

  QUnit.test("fetches a CSRF token first, then POSTs {prompt} with it", async function (assert) {
    var ctx = realClient([csrfOk("tok-1"), response({ body: { text: "answer", rows: [{ a: 1 }] } })]);
    var reply = await ctx.client.send("  list orders ");

    assert.deepEqual(reply, { text: "answer" }, "only text is returned, rows are ignored");
    assert.strictEqual(ctx.fetch.calls.length, 2);

    var tokenCall = ctx.fetch.calls[0];
    assert.strictEqual(tokenCall.url, "workflow/");
    assert.strictEqual(tokenCall.init.method, "GET");
    assert.strictEqual(tokenCall.init.headers["X-CSRF-Token"], "Fetch");

    var postCall = ctx.fetch.calls[1];
    assert.strictEqual(postCall.url, "workflow/chat");
    assert.strictEqual(postCall.init.method, "POST");
    assert.strictEqual(postCall.init.headers["X-CSRF-Token"], "tok-1");
    assert.strictEqual(postCall.init.credentials, "same-origin");
    assert.deepEqual(JSON.parse(postCall.init.body), { prompt: "list orders" });
  });

  QUnit.test("reuses the CSRF token for later prompts", async function (assert) {
    var ctx = realClient([
      csrfOk(),
      response({ body: { text: "one" } }),
      response({ body: { text: "two" } })
    ]);
    await ctx.client.send("a");
    await ctx.client.send("b");
    var tokenFetches = ctx.fetch.calls.filter(function (c) {
      return c.init.method === "GET";
    });
    assert.strictEqual(tokenFetches.length, 1);
  });

  QUnit.test("a 403 refreshes the token once and retries", async function (assert) {
    var ctx = realClient([
      csrfOk("old"),
      response({ status: 403 }),
      csrfOk("new"),
      response({ body: { text: "ok after retry" } })
    ]);
    var reply = await ctx.client.send("hi");
    assert.strictEqual(reply.text, "ok after retry");
    assert.strictEqual(ctx.fetch.calls[3].init.headers["X-CSRF-Token"], "new");
  });

  QUnit.test("a 403 that persists becomes errorForbidden", async function (assert) {
    var ctx = realClient([
      csrfOk(),
      response({ status: 403 }),
      csrfOk(),
      response({ status: 403 })
    ]);
    await rejectsWith(assert, ctx.client.send("hi"), "errorForbidden");
  });

  QUnit.test("401 and an opaque redirect become errorSession", async function (assert) {
    var unauthorized = realClient([csrfOk(), response({ status: 401 })]);
    await rejectsWith(assert, unauthorized.client.send("hi"), "errorSession");

    var redirected = realClient([response({ status: 0, type: "opaqueredirect" })]);
    await rejectsWith(assert, redirected.client.send("hi"), "errorSession");
  });

  QUnit.test("5xx becomes errorGeneric", async function (assert) {
    var ctx = realClient([csrfOk(), response({ status: 502 })]);
    await rejectsWith(assert, ctx.client.send("hi"), "errorGeneric");
  });

  QUnit.test("non-JSON or missing text becomes errorBadResponse", async function (assert) {
    var badJson = realClient([csrfOk(), response({ badJson: true })]);
    await rejectsWith(assert, badJson.client.send("hi"), "errorBadResponse");

    var noText = realClient([csrfOk(), response({ body: { result: "x" } })]);
    await rejectsWith(assert, noText.client.send("hi"), "errorBadResponse");
  });

  QUnit.test("a network failure becomes errorNetwork", async function (assert) {
    var ctx = realClient([new TypeError("Failed to fetch")]);
    await rejectsWith(assert, ctx.client.send("hi"), "errorNetwork");
  });

  QUnit.test("a request that outlives the timeout becomes errorTimeout", async function (assert) {
    var neverAnswers = function (sUrl, mInit) {
      return new Promise(function (resolve, reject) {
        mInit.signal.addEventListener("abort", function () {
          var oAbort = new Error("aborted");
          oAbort.name = "AbortError";
          reject(oAbort);
        });
      });
    };
    var client = new ChatClient({ mock: false, fetch: neverAnswers, timeoutMs: 10 });
    await rejectsWith(assert, client.send("hi"), "errorTimeout");
  });
});
