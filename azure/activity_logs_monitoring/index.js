// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2018 Datadog, Inc.

var tls = require('tls');
var DD_API_KEY = process.env.DD_API_KEY || '<your-api-key>';
var DD_URL = process.env.DD_URL || 'lambda-intake.logs.datadoghq.com';
var DD_TAGS = process.env.DD_TAGS || '';
var DD_PORT = process.env.DD_PORT || 10516;
var DD_SERVICE = process.env.DD_SERVICE || 'azure';
var DD_SOURCE = process.env.DD_SOURCE || 'azure';
var DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';

module.exports = function (context, eventHubMessages) {
    if (DD_API_KEY === '<your-api-key>' || DD_API_KEY === '' || DD_API_KEY === undefined) {
        context.log('You must configure your API key before starting this function (see #Parameters section)');
    }

    var socket = connectToDDSocket(context);

    eventHubMessages.forEach( message => {
        message.records.forEach( record => {
            addTags(record, context);
            if (!send(socket, record)) {
                // Retry once
                socket = connectToDDSocket(context);
                send(socket, record);
            }
        })
    })
    socket.end()
    context.done();
};

function addTags(record, context) {
    record['ddsource'] = DD_SOURCE;
    record['ddsourcecategory'] = DD_SOURCE_CATEGORY;
    record['service'] = DD_SERVICE;
    record['ddtags'] = [DD_TAGS, 'forwardername:' + context.executionContext.functionName].filter(Boolean).join(',');
}

function connectToDDSocket(context) {
    var socket = tls.connect({port: DD_PORT, host: DD_URL});
    socket.on('error', err => {
        context.log.error(err.toString());
        socket.end();
    });

    return socket;
}

function send(socket, record) {
    return socket.write(DD_API_KEY + ' ' + JSON.stringify(record) + '\n');
}
