const int IN1 = 5;
const int IN2 = 4;
const int IN3 = 14;
const int IN4 = 12;

const int pins[4] = {IN1, IN2, IN3, IN4};

const int sequence[8][4] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1}
};

const int STEPS_PER_REV = 4096;
const int STEP_DELAY_US = 1500;

void setup() {
  for (int i = 0; i < 4; i++) {
    pinMode(pins[i], OUTPUT);
  }
}

void release() {
  for (int i = 0; i < 4; i++) {
    digitalWrite(pins[i], LOW);
  }
}

void rotate(int steps, bool clockwise) {
  static int phase = 0;
  for (int s = 0; s < steps; s++) {
    phase = clockwise ? (phase + 1) % 8 : (phase + 7) % 8;
    for (int i = 0; i < 4; i++) {
      digitalWrite(pins[i], sequence[phase][i]);
    }
    delayMicroseconds(STEP_DELAY_US);
    yield();
  }
  release();
}

void loop() {
  rotate(STEPS_PER_REV, true);
  delay(1000);
  rotate(STEPS_PER_REV, false);
  delay(1000);
}
