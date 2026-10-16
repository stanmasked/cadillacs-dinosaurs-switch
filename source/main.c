#include <switch.h>
#include <stdio.h>
int main(int argc, char **argv) {
    consoleInit(NULL);
    printf("Cadillacs and Dinosaurs - Switch HD Remake\n");
    printf("Native technical bootstrap v0.1\n\n");
    printf("Target: World 930201 / CPS-1 / dino\n");
    printf("Gameplay is not implemented yet.\n");
    printf("Press PLUS to exit.\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    while (appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        consoleUpdate(NULL);
    }
    consoleExit(NULL);
    return 0;
}
