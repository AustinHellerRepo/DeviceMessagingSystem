from src.austin_heller_repo.esp32_processor_factory import ServerSocketFactory, Esp32ProcessorFactory, ApiInterfaceFactory


_ip_address = "0.0.0.0"
_port = 24776
_connections_total = 3
_to_dequeuer_or_reporter_packet_bytes_length = 1024
_listening_limit_total = 10
_accept_timeout_seconds = 1.0
_client_read_failed_delay_seconds = 0.1
_wifi_settings_file_path = "/wifi_settings.json"
_git_clone_directory_path = "/devices"
_initial_purpose_settings_file_path = "/initial_purpose_settings.json"

_server_socket_factory = ServerSocketFactory(
	to_client_packet_bytes_length=_to_dequeuer_or_reporter_packet_bytes_length,
	listening_limit_total=_listening_limit_total,
	accept_timeout_seconds=_accept_timeout_seconds,
	client_read_failed_delay_seconds=_client_read_failed_delay_seconds
)

_api_interface_factory = ApiInterfaceFactory(
	api_base_url="0.0.0.0:80"
)

_processor_factory = Esp32ProcessorFactory(
	host_ip_address=_ip_address,
	host_port=_port,
	server_socket_factory=_server_socket_factory,
	accepting_connections_total=_connections_total,
	wifi_settings_json_file_path=_wifi_settings_file_path,
	api_interface_factory=_api_interface_factory,
	purpose_git_clone_directory_path=_git_clone_directory_path,
	initial_purpose_settings_file_path=_initial_purpose_settings_file_path
)

_processor = _processor_factory.get_esp32_processor()
_processor.start()
