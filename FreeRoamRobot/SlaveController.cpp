// ===== SlaveController.cpp =====
#include "SlaveController.h"

void SlaveController::begin(SkidSteerMotors* m, WaterPump* p) {
    motors_ = m;
    pump_   = p;
    motors_->stop();
}

void SlaveController::update(PiCommand& cmd) {
    if (!cmd.fresh) return;
    switch (cmd.type) {
        case CMD_STOP:
        case CMD_ROAM:       motors_->stop(); break;
        case CMD_FORWARD:    motors_->forward   (cmd.speed ? cmd.speed : SPEED_CRUISE);   break;
        case CMD_REVERSE:    motors_->reverse   (cmd.speed ? cmd.speed : SPEED_REVERSE);  break;
        case CMD_TURN_LEFT:  motors_->pointTurnLeft (cmd.speed ? cmd.speed : SPEED_TURN); break;
        case CMD_TURN_RIGHT: motors_->pointTurnRight(cmd.speed ? cmd.speed : SPEED_TURN); break;
        case CMD_PUMP_ON:    pump_->on();  break;
        case CMD_PUMP_OFF:   pump_->off(); break;
        default: break;
    }
}
