.PHONY: sync
sync:
	@rsync \
	--archive \
	--compress \
	--exclude={'.mypy_cache'} \
	--partial \
	--progress \
	--delete \
	./ pi@raspberrypi.local:/home/pi/rotary-phone-hack

.PHONY: run
run:
	@PYGAME_HIDE_SUPPORT_PROMPT=1 python3 phonehack
