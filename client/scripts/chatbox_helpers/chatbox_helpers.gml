function get_command(_input_string) {
    var _space_index = string_pos(" ", _input_string);
    if (_space_index != 0)
        return string_copy(_input_string, 1, _space_index - 1);
    return _input_string;
}

function get_args(_input_string) {
	var _command = get_command(_input_string);
	var _headless_input_string = string_replace(_input_string, _command, "");
	return string_split(_headless_input_string, " ", true);
}

function chatbox_process_command(_input_string) {
	var _command = get_command(_input_string);
	var _args = get_args(_input_string);
    switch (_command) {
        case "/login":
            handle_login(_args);
            break;
        case "/register":
            handle_register(_args);
            break;
		case "/logout":
			handle_logout(_args);
			break;
        default:
            obj_network_client.send_packet({
				chat: {
					to_pid: obj_network_client.everyone, 
					message: _input_string	
				}
			});
            break;
    }
}

function handle_login(_args) {
	obj_statemachine.state = state_login;;
    if (array_length(_args) != 2) {
        add_to_log("Usage: /login username password", c_yellow);
    } else {
        obj_network_client.send_packet({
			login: {
				username: _args[0],
				password: _args[1]
			}
		});
    }
}

function handle_register(_args) {
	obj_statemachine.state = state_register;
    if (array_length(_args) != 2) {
        add_to_log("Usage: /register username password", c_yellow);
    } else {
        obj_network_client.send_packet({
			register: {
				username: _args[0],
				password: _args[1]
			}
		});
    }
}

function handle_logout(_args) {
	obj_statemachine.state = state_entry;
	if (array_length(_args) != 0) {
		add_to_log("Usage: /logout", c_yellow);	
	} else {
		obj_network_client.send_packet({
			disconnect: {
				to_pid: obj_network_client.everyone,
				reason: "user logged out"
			}
		});
		game_restart();
	}
}