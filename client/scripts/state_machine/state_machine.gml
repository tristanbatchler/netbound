function state_entry(_packet_name, _packet_data) {
	switch (_packet_name) {
		case "Pid":
			obj_network_client.pid = pid_to_string(_packet_data.from_pid);
			obj_chatbox.add_to_log("Received PID from server: " + obj_network_client.pid);
			break;
		}	
}

function state_login(_packet_name, _packet_data) {
	switch (_packet_name) {
		case "Ok":
			obj_chatbox.add_to_log("Logged in successfully", c_lime);
			obj_statemachine.state = state_play;
			break;
		case "Deny":
			var _reason = _packet_data.reason;
			obj_chatbox.add_to_log("Cannot login: " + _reason, c_yellow);
			break;
	}
}

function state_register(_packet_name, _packet_data) {
		switch (_packet_name) {
		case "Ok":
			obj_chatbox.add_to_log("Registered successfully", c_lime);	
			break;
		case "Deny":
			var _reason = _packet_data.reason;
			obj_chatbox.add_to_log("Cannot register: " + _reason, c_yellow);	
			break;
	}
}

function state_play(_packet_name, _packet_data) {
	switch (_packet_name) {
		case "Chat":
			var _sender = struct_get(known_others, _packet_data.from_pid)
			var _message = _packet_data.message;
			obj_chatbox.add_to_log(_sender.name + ": " + _message);
			break;
				
		case "Hello":
			var _from_pid = pid_to_string(_packet_data.from_pid);
			var _state_view = _packet_data.state_view;
			
			if (_from_pid == obj_network_client.pid) { // This is information about our own player
				instance_create_layer(0, 0, "Instances", obj_player);
				obj_player.x = _state_view.x;
				obj_player.y = _state_view.y;
				obj_player.name = _state_view.name;
				
				obj_chatbox.add_to_log("Welcome back, " + obj_player.name);
			} else {
				struct_set(obj_network_client.known_others, _from_pid, _state_view);
				var _other = instance_create_layer(0, 0, "Instances", obj_actor, _state_view);
				obj_chatbox.add_to_log(_other.name + " has joined");
			}
			break;
	}
}