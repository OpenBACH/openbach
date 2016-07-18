FLAGS=-pthread -std=c++11 -pedantic
ASIO_FLAGS=-DASIO_STANDALONE -I./dependencies/asio-1.10.6/include
BUILD_FLAGS=-fPIC -DGENERATE_LIB

all: build/librstats.so build/libsyslog_wrapper.so

build/rstats.o: ./src/rstats.cpp ./src/rstats.h ./src/logger.h
	g++ ${FLAGS} ${ASIO_FLAGS} ${BUILD_FLAGS} -c $< -o $@

build/logger.o: ./src/logger.cpp ./src/logger.h
	g++ ${FLAGS} ${BUILD_FLAGS} -c $< -o $@

build/librstats.so: ./build/rstats.o ./build/libsyslog_wrapper.so
	g++ -shared ${FLAGS} -o $@ -L./build -lsyslog_wrapper $<
 
build/libsyslog_wrapper.so: ./build/logger.o
	g++ -shared ${FLAGS} -o $@ $^

install: all
	cp build/librstats.so build/libsyslog_wrapper.so src/*.h $(if ${DESTDIR}, ${DESTDIR}, .)

clean:
	@rm -f *.o
	@rm -f *.so
