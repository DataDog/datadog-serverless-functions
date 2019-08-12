main: init test clean

init:
	pip3 install -r requirements.txt

clean:	
	find . -type d -name __pycache__ -exec rm -rf {} \+
	rm -rf .pytest_cache

test:
	python3 -m pytest tests/
