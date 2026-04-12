.PHONY: install dev run test

install:
	python -m media_tools.devtools install

dev:
	python -m media_tools.devtools dev

run:
	python -m media_tools.devtools run

test:
	python -m media_tools.devtools test
