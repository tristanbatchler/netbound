var _input_x = keyboard_check(vk_right) - keyboard_check(vk_left);
var _input_y = keyboard_check(vk_down) - keyboard_check(vk_up);
var _speed = 5;

x += _input_x * _speed;
y += _input_y * _speed;