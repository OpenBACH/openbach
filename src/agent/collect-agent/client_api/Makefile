BUILD_FLAGS=-pthread -std=c++11 -pedantic -Wall -Wextra -Werror -fPIC $(CXXFLAGS) -DGENERATE_LIB
ASIO_FLAGS=-DASIO_STANDALONE -I./dependencies/asio-1.10.6/include
LIBS_FLAGS=-pthread $(LDLIBS)

DESTINATION=$(if ${DESTDIR}, ${DESTDIR}, /usr/)

all: build/libcollectagent.so

build/collectagent.o: ./src/collectagent.cpp ./src/collectagent.h ./src/syslog.h
	@mkdir -p build
	g++ $(CPPFLAGS) ${BUILD_FLAGS} ${ASIO_FLAGS} -c $< -o $@

build/libcollectagent.so: ./build/collectagent.o
	@mkdir -p build
	g++ -o $@ $< $(LDFLAGS) -shared ${LIBS_FLAGS}

install: all
	mkdir -p ${DESTINATION}/{lib,include}/
	cp build/libcollectagent.so ${DESTINATION}/lib/
	cp src/collectagent.h ${DESTINATION}/include/

clean:
	@rm -rf build/

uninstall:
	@rm -f ${DESTINATION}/lib/libcollectagent.so
	@rm -f ${DESTINATION}/include/collectagent.h
