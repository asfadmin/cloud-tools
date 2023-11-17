PACKAGES := \
	destroy-cumulus \
	remotezip-cli \
	test-cnm

TOX_INIS := $(PACKAGES:%=%/tox.ini)


%/tox.ini: tox.ini.tmpl
	cp $< $@

.PHONY: tests
tests: $(TOX_INIS)
	ss=0; $(foreach package,$(PACKAGES),cd $(package) && tox || ss=1;cd ..;) exit $$ss
