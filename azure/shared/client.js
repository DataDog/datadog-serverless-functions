// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2019 Datadog, Inc.

var tls = require('tls')

var DD_PORT = require('./env.js').DD_PORT;
var DD_URL = require('./env.js').DD_URL;
var DD_API_KEY = require('./env.js').DD_API_KEY;


function getSocket(context) {
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

module.exports = {
  getSocket,
  send,
};
