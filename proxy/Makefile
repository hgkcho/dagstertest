.PHONY: build-to-deploy
build-to-deploy: build deploy

.PHONY: build
build:
	cargo lambda build --release

.PHONY: deploy
deploy:
	cargo lambda deploy
