"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const DESTINATION = "AWSService-CTC-NoSSO";
const files = {
  approuter: path.join(__dirname, "xs-app.json"),
  uiBundled: path.join(__dirname, "..", "ui", "webapp", "xs-app.json")
};

for (const [label, file] of Object.entries(files)) {
  const config = JSON.parse(fs.readFileSync(file, "utf8"));
  const routes = config.routes.map((r) => ({ ...r, regex: new RegExp(r.source) }));
  const firstMatch = (url) => routes.find((r) => r.regex.test(url));

  test(`${label}: /workflow paths go to the workflow destination`, () => {
    for (const url of ["/workflow", "/workflow/", "/workflow/chat", "/ecc-app-1.0.0/workflow/chat"]) {
      const route = firstMatch(url);
      assert.strictEqual(route.destination, DESTINATION, url);
    }
  });

  test(`${label}: other paths are served from the HTML5 repo`, () => {
    for (const url of ["/index.html", "/workflowx", "/other/chat", "/ecc-app-1.0.0/index.html"]) {
      const route = firstMatch(url);
      assert.strictEqual(route.service, "html5-apps-repo-rt", url);
    }
  });

  test(`${label}: workflow routes need login, CSRF and a viewer scope`, () => {
    for (const route of routes.filter((r) => r.destination === DESTINATION)) {
      assert.strictEqual(route.authenticationType, "xsuaa");
      assert.strictEqual(route.csrfProtection, true);
      assert.deepStrictEqual(route.scope, ["$XSAPPNAME.SalesRead", "$XSAPPNAME.PurchasingRead"]);
    }
  });

  test(`${label}: the workflow prefix is stripped from the forwarded path`, () => {
    const route = firstMatch("/workflow/chat");
    const forwarded = "/workflow/chat".replace(route.regex, route.target);
    assert.strictEqual(forwarded, "/chat");
    const versioned = "/ecc-app-1.0.0/workflow/chat".replace(firstMatch("/ecc-app-1.0.0/workflow/chat").regex, "$1");
    assert.strictEqual(versioned, "/chat");
  });
}
