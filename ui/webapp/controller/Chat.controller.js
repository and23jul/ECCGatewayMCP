sap.ui.define([
  "sap/ui/core/mvc/Controller",
  "sap/ui/model/json/JSONModel",
  "sap/ui/core/InvisibleMessage",
  "sap/ui/core/library",
  "aps/pco/eccgatewaychat/util/ChatClient"
], function (Controller, JSONModel, InvisibleMessage, coreLibrary, ChatClient) {
  "use strict";

  var SUGGESTION_COUNT = 4;
  var ANNOUNCE_MAX_CHARS = 500;

  return Controller.extend("aps.pco.eccgatewaychat.controller.Chat", {

    onInit: function () {
      this._client = new ChatClient();
      this._bundle = this.getOwnerComponent().getModel("i18n").getResourceBundle();

      var aSuggestions = [];
      for (var i = 1; i <= SUGGESTION_COUNT; i++) {
        aSuggestions.push({ text: this._bundle.getText("suggestion" + i) });
      }

      this._model = new JSONModel({
        messages: [],
        suggestions: aSuggestions,
        prompt: "",
        canSend: false,
        busy: false,
        error: "",
        mock: this._client.isMock()
      });
      this.getView().setModel(this._model, "chat");

      // Enter sends. Shift+Enter is a different UI5 pseudo event (sapentermodifiers),
      // so it keeps its default behaviour and adds a new line.
      this.byId("promptInput").addEventDelegate({ onsapenter: this._onEnter }, this);
    },

    onPromptChange: function (oEvent) {
      this._model.setProperty("/canSend", oEvent.getParameter("value").trim().length > 0);
    },

    onSend: function () {
      this._submit(this._model.getProperty("/prompt"));
    },

    onSuggestion: function (oEvent) {
      var sText = oEvent.getSource().getBindingContext("chat").getProperty("text");
      this._submit(sText);
    },

    onNewChat: function () {
      this._model.setProperty("/messages", []);
      this._model.setProperty("/error", "");
      this._model.setProperty("/prompt", "");
      this._model.setProperty("/canSend", false);
      this.byId("promptInput").focus();
    },

    onCloseError: function () {
      this._model.setProperty("/error", "");
    },

    _onEnter: function (oEvent) {
      // Do not hijack Enter while an IME composition (e.g. CJK input) is confirming text.
      if (oEvent.originalEvent && oEvent.originalEvent.isComposing) {
        return;
      }
      oEvent.preventDefault();
      this.onSend();
    },

    _submit: async function (sPrompt) {
      var sClean = (sPrompt || "").trim();
      if (!sClean || this._model.getProperty("/busy")) {
        return;
      }

      this._model.setProperty("/error", "");
      this._addMessage("user", sClean);
      this._model.setProperty("/prompt", "");
      this._model.setProperty("/canSend", false);
      this._model.setProperty("/busy", true);
      this._scrollToEnd();

      try {
        var oReply = await this._client.send(sClean);
        this._addMessage("assistant", oReply.text);
        InvisibleMessage.getInstance().announce(
          oReply.text.slice(0, ANNOUNCE_MAX_CHARS),
          coreLibrary.InvisibleMessageMode.Polite
        );
      } catch (oError) {
        this._model.setProperty("/error", this._errorText(oError));
      } finally {
        this._model.setProperty("/busy", false);
        this._scrollToEnd();
        this.byId("promptInput").focus();
      }
    },

    _addMessage: function (sRole, sText) {
      var aMessages = this._model.getProperty("/messages").slice();
      aMessages.push({
        role: sRole,
        text: sText,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      });
      this._model.setProperty("/messages", aMessages);
    },

    _errorText: function (oError) {
      var sKey = oError && oError.messageKey;
      return this._bundle.getText(sKey && this._bundle.hasText(sKey) ? sKey : "errorGeneric");
    },

    _scrollToEnd: function () {
      // Wait one render pass so the new row is part of the scroll height.
      setTimeout(function () {
        this.byId("messageScroller").scrollTo(0, 1000000, 200);
      }.bind(this), 50);
    }
  });
});
