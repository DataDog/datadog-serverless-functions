// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2018 Datadog, Inc.

var tls = require('tls');

module.exports = function dd (context, eventHubMessages) {
    var apiKey = "<your-api-key>";
    var ddUrl = "intake.logs.datadoghq.com";
    var port = 10516;

    if (apiKey === "<your-api-key>" || apiKey === "") {
        context.log("You must configure your API key before starting this function (see #Parameters section)")
    }

    var socket = tls.connect({port: port, host: ddUrl});
    eventHubMessages.forEach( message => {
        message.records.forEach( record => {
            socket.write(apiKey + " " + JSON.stringify(record) +'\n');
            })
    })
    socket.end()
    context.done();
};
