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
