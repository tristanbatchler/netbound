function get_command(_input_string) {
    var _space_index = string_pos(" ", _input_string);
    if (_space_index != 0)
        return string_copy(_input_string, 1, _space_index - 1);
    return _input_string;
}

function chatbox_process_command(_input_string) {
	var _command = get_command(_input_string);
    switch (_command) {
        case "/login":
            handle_login(_input_string);
            break;
        case "/register":
            handle_register(_input_string);
            break;
        default:
            obj_network_client.send_packet({
				chat: {
					to_pid: obj_network_client.EVERYONE, 
					message: _input_string	
				}
			});
            break;
    }
}

function handle_login(_input_string) {
	var _array = string_split(_input_string, " ");
    if (array_length(_array) != 3) {
        add_to_log("Usage: /login username password", c_yellow);
    } else {
        obj_network_client.send_packet({
			login: {
				username: _array[1],
				password: _array[2]
			}
		});
    }
}

function handle_register(_input_string) {
	var _array = string_split(_input_string, " ");
    if (array_length(_array) != 3) {
        add_to_log("Usage: /register username password", c_yellow);
    } else {
        obj_network_client.send_packet({
			register: {
				username: _array[1],
				password: _array[2]
			}
		});
    }
}