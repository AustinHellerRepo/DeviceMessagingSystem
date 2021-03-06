from __future__ import annotations
from austin_heller_repo.api_interface import ApiInterfaceFactory, ApiInterface
from austin_heller_repo.socket_client_factory import ServerSocketFactory, ServerSocket, start_thread, ClientSocketFactory, ClientSocket, json, threading, Semaphore, ThreadDelay
from typing import List, Tuple, Dict, Callable
import time


class Dequeuer():

	def __init__(self, *,
				 dequeuer_guid: str,
				 queue_guid: str,
				 api_interface_factory: ApiInterfaceFactory,
				 server_socket_factory: ServerSocketFactory,
				 client_socket_factory: ClientSocketFactory,
				 wifi_server_polling_seconds: float,
				 is_informed_of_enqueue: bool,
				 listening_port: int):

		self.__dequeuer_guid = dequeuer_guid
		self.__queue_guid = queue_guid
		self.__api_interface_factory = api_interface_factory
		self.__server_socket_factory = server_socket_factory
		self.__client_socket_factory = client_socket_factory
		self.__wifi_server_polling_seconds = wifi_server_polling_seconds
		self.__is_informed_of_enqueue = is_informed_of_enqueue
		self.__listening_port = listening_port

		self.__server_socket = None  # type: ServerSocket
		self.__process_thread = None  # type: threading.Thread
		self.__is_running_process_thread = False
		self.__process_transmission_dequeue_threads = []  # type: List[threading.Thread]
		self.__process_transmission_dequeue_threads_semaphore = Semaphore()

		self.__start_semaphore = Semaphore()
		self.__is_running_transmission_dequeue_thread = False
		self.__transmission_dequeue_thread = None
		self.__transmission_dequeue_thread_delay = None
		self.__wifi_server_token_guid = None  # type: str

	def is_running(self) -> bool:
		return self.__is_running_process_thread

	def start(self):

		self.__start_semaphore.acquire()
		if self.__transmission_dequeue_thread is not None:
			raise Exception("Cannot start without first stopping.")
		else:

			def _on_accepted_wifi_server_client_method(client_socket: ClientSocket) -> bool:
				# wifi server connected to dequeuer to inform them that a transmission is available
				_is_client_valid = None
				try:
					_wifi_server_json_string = client_socket.read()
					client_socket.close()

					_is_client_valid = False

					_wifi_server_json = json.loads(_wifi_server_json_string)

					if "wifi_server_token_guid" not in _wifi_server_json:
						_error = "Missing wifi_server_token_guid from client socket json object. \"" + _wifi_server_json_string + "\"."
						print(_error)
					else:
						_wifi_server_token_guid = _wifi_server_json["wifi_server_token_guid"]
						if _wifi_server_token_guid != self.__wifi_server_token_guid:
							_error = "Invalid wifi server token: \"" + _wifi_server_token_guid + "\"."
							print(_error)
						else:
							self.__transmission_dequeue_thread_delay.try_abort()
							_is_client_valid = True
				except Exception as ex:
					print("ex: " + str(ex))
				return _is_client_valid

			self.__server_socket = self.__server_socket_factory.get_server_socket()
			self.__server_socket.start_accepting_clients(
				host_ip_address="0.0.0.0",
				host_port=self.__listening_port,
				on_accepted_client_method=_on_accepted_wifi_server_client_method
			)

			def _transmission_dequeue_thread_method():
				while self.__is_running_transmission_dequeue_thread and not self.try_announce_dequeuer():
					self.__transmission_dequeue_thread_delay.try_sleep(self.__wifi_server_polling_seconds)
				while self.__is_running_transmission_dequeue_thread:
					_is_normal_sleep = self.__transmission_dequeue_thread_delay.try_sleep(self.__wifi_server_polling_seconds)
					_found_transmission_dequeue = self.try_process_next_transmission_dequeue(
						queue_guid=self.__queue_guid
					)
			self.__transmission_dequeue_thread = start_thread(_transmission_dequeue_thread_method)

		self.__start_semaphore.release()

	def stop(self):

		self.__start_semaphore.acquire()
		if self.__transmission_dequeue_thread is None:
			raise Exception("Cannot stop without first starting.")
		else:

			self.__is_running_transmission_dequeue_thread = False
			self.__transmission_dequeue_thread_delay.try_abort()
			self.__transmission_dequeue_thread.join()
			self.__transmission_dequeue_thread = None

		self.__start_semaphore.release()

	def BACKUP_start(self):

		self.__is_running_process_thread = True

		if self.__process_thread is not None:
			raise Exception(f"Cannot start dequeuer without first stopping previous start.")
		else:

			def _on_accepted_wifi_server_client_method(client_socket: ClientSocket):
				# wifi server connected to dequeuer to inform them that a transmission is available
				_wifi_server_json_string = client_socket.read()
				client_socket.close()
				_wifi_server_json = json.loads(_wifi_server_json_string)
				if "queue_guid" in _wifi_server_json:
					_error = "\"queue_guid\" is missing from json sent to dequeuer: \"" + _wifi_server_json_string + "\""
					print(_error)
					raise Exception(_error)
				_queue_guid = _wifi_server_json["queue_guid"]
				if _queue_guid in self.__queue_guids:
					self.try_process_next_transmission_dequeue(
						queue_guid=_queue_guid
					)

			self.__server_socket = self.__server_socket_factory.get_server_socket()
			self.__server_socket.start_accepting_clients(
				host_ip_address="0.0.0.0",
				host_port=self.__listening_port,
				on_accepted_client_method=_on_accepted_wifi_server_client_method
			)

			def _process_thread_method():
				try:
					_annouce_is_successful = False
					while not _annouce_is_successful:
						_annouce_is_successful = self.try_announce_dequeuer()
						if not _annouce_is_successful:
							time.sleep(self.__wifi_server_polling_seconds)
						else:
							_process_dequeue_index = 0
							while self.__is_running_process_thread:
								for _queue_guid in self.__queue_guids:
									_dequeue_is_successful = self.try_process_next_transmission_dequeue(
										queue_guid=_queue_guid
									)
									if not _dequeue_is_successful:
										time.sleep(self.__wifi_server_polling_seconds)
									else:
										print(f"Processed transmission dequeue #{_process_dequeue_index}")
										_process_dequeue_index += 1
								self.join_completed_transmission_dequeue_threads()
					self.__is_running_process_thread = False
					self.join_all_transmission_dequeue_threads()
				except Exception as ex:
					print("ex: " + str(ex))
					self.__is_running_process_thread = False

			self.__process_thread = start_thread(_process_thread_method)

	def try_announce_dequeuer(self) -> bool:
		_is_successful = False
		try:
			_api_interface = self.__api_interface_factory.get_api_interface()
			_api_interface.send_dequeuer_announcement(
				dequeuer_guid=self.__dequeuer_guid,
				is_informed_of_enqueue=self.__is_informed_of_enqueue,
				listening_port=self.__listening_port
			)
			_is_successful = True
		except Exception as ex:
			print(f"try_announce_dequeuer: ex: {ex}")
		return _is_successful

	def try_process_next_transmission_dequeue(self, *, queue_guid: str) -> bool:
		_is_successful = False
		try:
			_api_interface = self.__api_interface_factory.get_api_interface()
			_transmission_dequeue = _api_interface.dequeue_next_transmission(
				dequeuer_guid=self.__dequeuer_guid,
				queue_guid=queue_guid
			)
			if _transmission_dequeue is not None:

				def _process_transmission_dequeue_thread_method(transmission_dequeue: Dict, api_interface: ApiInterface):
					_transmission_dequeue_guid = None
					try:
						_transmission_dequeue_guid = transmission_dequeue["transmission_dequeue_guid"]
						_transmission = transmission_dequeue["transmission"]
						_destination_device = _transmission["destination_device"]
						_destination_client = _destination_device["last_known_client"]
						_ip_address = _destination_client["ip_address"]
						_port = _destination_device["socket_port"]
						_client_socket = self.__client_socket_factory.get_client_socket()
						_client_socket.connect_to_server(
							ip_address=_ip_address,
							port=_port
						)
						_transmission_json_string = _transmission["transmission_json_string"]
						_client_socket.write(_transmission_json_string)
						_client_socket.close()
						api_interface.update_transmission_as_completed(
							transmission_dequeue_guid=_transmission_dequeue_guid
						)

						# force the dequeuer to immediately dequeue next transmission
						self.__transmission_dequeue_thread_delay.try_abort()

					except Exception as ex:
						print(f"ex: {ex}")
						_error_message_json = {"exception": str(ex), "transmission_dequeue_guid": _transmission_dequeue_guid}
						if _transmission_dequeue_guid is None:
							print("Error: failed to send update of failure to api since _transmission_dequeue_guid is None.")
						else:
							api_interface.update_transmission_as_failed(
								transmission_dequeue_guid=_transmission_dequeue_guid,
								error_message_json=_error_message_json
							)

				_process_transmission_dequeue_thread = start_thread(_process_transmission_dequeue_thread_method, _transmission_dequeue, _api_interface)
				self.__process_transmission_dequeue_threads_semaphore.acquire()
				self.__process_transmission_dequeue_threads.append(_process_transmission_dequeue_thread)
				self.__process_transmission_dequeue_threads_semaphore.release()

				_is_successful = True
		except Exception as ex:
			print(f"try_process_next_transmission_dequeue: ex: {ex}")
		return _is_successful

	def stop(self):

		if self.__process_thread is None:
			_error = f"Cannot stop processing without first starting."
			print(_error)
			raise Exception(_error)
		else:
			self.__server_socket.stop_accepting_clients()
			self.__server_socket.close()
			self.__is_running_process_thread = False
			self.__process_thread.join()

	def join_completed_transmission_dequeue_threads(self):

		_remove_indexes = []  # type: List[int]

		for _thread_index in range(len(self.__process_transmission_dequeue_threads)):
			if not self.__process_transmission_dequeue_threads[_thread_index].is_alive():
				_remove_indexes.append(_thread_index)

		self.__process_transmission_dequeue_threads_semaphore.acquire()
		for _thread_index in reversed(_remove_indexes):
			self.__process_transmission_dequeue_threads.pop(_thread_index)
		self.__process_transmission_dequeue_threads_semaphore.release()

	def join_all_transmission_dequeue_threads(self):

		self.__process_transmission_dequeue_threads_semaphore.acquire()
		for _thread in self.__process_transmission_dequeue_threads:
			_thread.join()
		self.__process_transmission_dequeue_threads.clear()
		self.__process_transmission_dequeue_threads_semaphore.release()
