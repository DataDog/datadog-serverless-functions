import os
import unittest
from lambda_function import concatenate_multiline_logs


def example_event_data(*args, **kwargs):
    temp = {}
    temp["logGroup"] = '/aws/lambda/examplefunction'
    temp["logEvents"] = [ { "id": '34912906382115817415310389072300611503980664147748519936',
           "timestamp": 1565548867148,
           "message": 'this is a test ruby\n' },
         { "id": '34912906382115817415310389072300611503980664147748519937',
           "timestamp": 1565548867148,
           "message":
            'I, [2019-08-11T18:41:07.146332 #8]  INFO -- initialize: Initializing...\n' },
         { "id": '34912906382115817415310389072300611503980664147748519938',
           "timestamp": 1565548867148,
           "message":
            'I, [2019-08-11T18:41:07.148625 #8]  INFO -- info: ["/var/task/lambda_function.rb:15:in `lambda_handler\'", "/var/runtime/lib/lambda_handler.rb:24:in `call_handler\'", "/var/runtime/lib/runtime.rb:42:in `<main>\'"]\n' },
         { "id": '34912906382115817415310389072300611503980664147748519939',
           "timestamp": 1565548867148,
           "message":
            'E, [2019-08-11T18:41:07.148721 #8] ERROR -- error: #<NoMethodError: undefined method `made_up_function\' for #<LambdaHandler:0x00005650394a41d0>> \r slash r \n' },
         { "id": '34912906382115817415310389072300611503980664147748519940',
           "timestamp": 1565548867148,
           "message": ' slash n \r \n' },
         { "id": '34912906382115817415310389072300611503980664147748519941',
           "timestamp": 1565548867148,
           "message":
            ' undefined method `made_up_function\' for #<LambdaHandler:0x00005650394a41d0> \r \n' },
         { "id": '34912906382115817415310389072300611503980664147748519942',
           "timestamp": 1565548867148,
           "message":
            ' \r \n ["/var/task/lambda_function.rb:15:in `lambda_handler\'", "/var/runtime/lib/lambda_handler.rb:24:in `call_handler\'", "/var/runtime/lib/runtime.rb:42:in `<main>\'"]\n' },
         { "id": '34912906382584133064479532158272861587706279739374108679',
           "timestamp": 1565548867169,
           "message": 'END Request"Id: b1969047-01c5-4782-973c-2a0741857a2c\n' },
         { "id": '34912906382584133064479532158272861587706279739374108680',
           "timestamp": 1565548867169,
           "message":
            'REPORT RequestId: b1969047-01c5-4782-973c-2a0741857a2c\tDuration: 23.61 ms\tBilled Duration: 100 ms \tMemory Size: 128 MB\tMax Memory Used: 45 MB\t\n' } ]

    return temp

def mock_validation(*args, **kwargs):
    return {'ok':'ok'}

class ConcatenateMultilineLogs(unittest.TestCase):
    def test_concatenate_multiline_logs(self):
        event_data = example_event_data()
        response = concatenate_multiline_logs(event_data)
        self.assertEqual(isinstance(response, list), True, 'should return a list of logs')

if __name__ == '__main__':
    unittest.main()
