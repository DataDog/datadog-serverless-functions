// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2019 Datadog, Inc.

const VERSION = '0.1.0';
var client = require('../Shared/client.js');

module.exports = function(context, eventHubMessages) {
    if (VERSION !== client.VERSION) {
        context.log.warn(
            `Function version (${VERSION}) is different from client library version (${
                client.VERSION
            }). Please upgrade your ${
                VERSION > client.VERSION ? 'client library' : 'function'
            }.`
        );
    }

    if (!client.DD_API_KEY || client.DD_API_KEY === '<DATADOG_API_KEY>') {
        context.log.error(
            'You must configure your API key before starting this function (see ## Parameters section)'
        );
        return;
    }

    var socket = client.getSocket(context);
    var sender = tagger => record => {
        record = tagger(record, context);
        if (!client.send(socket, record)) {
            // Retry once
            socket = client.getSocket(context);
            client.send(socket, record);
        }
    };

    client.handleLogs(sender, eventHubMessages, context);

    socket.end();
    context.done();
};
