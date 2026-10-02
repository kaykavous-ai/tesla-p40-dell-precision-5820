@echo -off
echo === Sultan Qaboos: SocketCommonRcConfig READ-ONLY dump ===
echo Nothing is written to NVRAM by this script.
echo.
echo --- current value (hex) ---
dmpstore -guid 4402ca38-808f-4279-bcec-5baf8d59092f SocketCommonRcConfig
echo.
echo --- saving a copy to fs0:\rc-before.bin (or fs1 if fs0 is not the stick) ---
dmpstore -guid 4402ca38-808f-4279-bcec-5baf8d59092f -s fs0:\rc-before.bin SocketCommonRcConfig
dmpstore -guid 4402ca38-808f-4279-bcec-5baf8d59092f -s fs1:\rc-before.bin SocketCommonRcConfig
echo.
echo --- BIOS/firmware identification ---
ver
echo.
echo Done. Copy the hex above (or rc-before.bin) to burnerrobot.
echo Type  reset  to reboot, or  exit  to return to the boot menu.
