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
