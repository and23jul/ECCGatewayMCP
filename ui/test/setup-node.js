/*
 * Lets the QUnit tests under webapp/test run in plain Node (`npm test`, no browser).
 * Provides a minimal `sap.ui.define` that loads our own modules from webapp/ by their
 * module name (aps/pco/eccgatewaychat/...). Only modules without UI5 library dependencies
 * (e.g. util/ChatClient) can be loaded this way.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const WEBAPP = path.resolve(__dirname, "..", "webapp");
const NAMESPACE = "aps/pco/eccgatewaychat/";
const cache = new Map();

function loadModule(name) {
  if (cache.has(name)) {
    return cache.get(name);
  }
  if (!name.startsWith(NAMESPACE)) {
    throw new Error(`setup-node: cannot load '${name}' (only ${NAMESPACE}* is supported)`);
  }
  const file = path.join(WEBAPP, `${name.slice(NAMESPACE.length)}.js`);
  const source = fs.readFileSync(file, "utf8");

  let exported;
  const sapStub = {
    ui: {
      define(deps, factory) {
        exported = factory(...deps.map(loadModule));
      }
    }
  };
  new Function("sap", source)(sapStub);

  cache.set(name, exported);
  return exported;
}

global.sap = {
  ui: {
    define(deps, factory) {
      factory(...deps.map(loadModule));
    }
  }
};
